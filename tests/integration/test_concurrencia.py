"""Test de concurrencia (SC-004): publicar 50 solicitudes simultaneas y verificar
que no hay perdida de eventos ni caida del proceso. Requiere RabbitMQ + PostgreSQL
reales (docker-compose.test.yml)."""

from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pika
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.anuncio import Base
from src.worker.events.consumer import Consumer
from src.worker.events.publisher import Publisher
from src.worker.reportes import repository as repository_module
from src.worker.reportes.excel_builder import construir_reporte

RABBITMQ_URL = os.environ.get("TEST_RABBITMQ_URL", "amqp://guest:guest@localhost:5673/")
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://reportes:reportes@localhost:5433/reportes"
)

QUEUE_GENERAR = "test.concurrencia.reporte.generar"
QUEUE_LISTO = "test.concurrencia.reporte.listo"
N_SOLICITUDES = 50


class _RepositoryAdapter:
    def __init__(self, session: Session):
        self._session = session

    def obtener_eventos_anuncio(self, anuncio_id, fecha_desde, fecha_hasta):
        return repository_module.obtener_eventos_anuncio(
            self._session, anuncio_id, fecha_desde, fecha_hasta
        )

    def anuncio_existe(self, anuncio_id):
        return repository_module.anuncio_existe(self._session, anuncio_id)


class _ExcelBuilderAdapter:
    @staticmethod
    def construir_reporte(eventos):
        return construir_reporte(eventos)


@pytest.fixture()
def engine():
    engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=10)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def rabbit_channel():
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_GENERAR, durable=True)
    channel.queue_declare(queue=QUEUE_LISTO, durable=True)
    channel.queue_purge(QUEUE_GENERAR)
    channel.queue_purge(QUEUE_LISTO)
    yield channel
    channel.queue_purge(QUEUE_GENERAR)
    channel.queue_purge(QUEUE_LISTO)
    connection.close()


def _insertar_evento(engine, anuncio_id):
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO anuncio (id, anuncio_id, tipo_evento, timestamp, usuario_id) "
                "VALUES (:id, :anuncio_id, 'impresion', :timestamp, 'user-1')"
            ),
            {
                "id": str(uuid.uuid4()),
                "anuncio_id": anuncio_id,
                "timestamp": datetime.now(timezone.utc) - timedelta(hours=1),
            },
        )


def test_50_solicitudes_concurrentes_no_pierden_eventos(engine, rabbit_channel):
    ahora = datetime.now(timezone.utc)
    solicitudes = []
    for _ in range(N_SOLICITUDES):
        anuncio_id = f"anuncio-{uuid.uuid4()}"
        _insertar_evento(engine, anuncio_id)
        payload = {
            "solicitud_id": str(uuid.uuid4()),
            "anuncio_id": anuncio_id,
            "fecha_desde": (ahora - timedelta(days=2)).isoformat(),
            "fecha_hasta": (ahora + timedelta(days=1)).isoformat(),
            "usuario_solicitante": "user-1",
        }
        solicitudes.append(payload)

    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    publish_channel = connection.channel()
    for payload in solicitudes:
        publish_channel.basic_publish(
            exchange="",
            routing_key=QUEUE_GENERAR,
            body=json.dumps(payload).encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
    connection.close()

    def _procesar_uno(_):
        conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        ch = conn.channel()
        with Session(engine) as session:
            repository = _RepositoryAdapter(session)
            publisher = Publisher(ch, QUEUE_LISTO)
            consumer = Consumer(
                channel=ch,
                repository=repository,
                excel_builder=_ExcelBuilderAdapter,
                publisher=publisher,
            )
            ch.basic_qos(prefetch_count=1)
            ch.basic_consume(queue=QUEUE_GENERAR, on_message_callback=consumer.procesar_mensaje)
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                conn.process_data_events(time_limit=0.5)
            ch.stop_consuming()
        conn.close()

    with ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(_procesar_uno, range(10)))

    resultados_recibidos = 0
    verify_conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    verify_channel = verify_conn.channel()
    while True:
        method, _, body = verify_channel.basic_get(queue=QUEUE_LISTO, auto_ack=True)
        if body is None:
            break
        resultados_recibidos += 1
    verify_conn.close()

    assert resultados_recibidos == N_SOLICITUDES
