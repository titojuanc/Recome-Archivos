"""Integration tests: recuperacion ante fallos transitorios (User Story 3).

Simula una falla de conexion a la DB a mitad de una consulta y verifica que el
mensaje no se hace ack (no se pierde). Requiere RabbitMQ + PostgreSQL reales.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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

QUEUE_GENERAR = "test.db.reporte.generar"
QUEUE_LISTO = "test.db.reporte.listo"


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
    engine = create_engine(DATABASE_URL)
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
    if connection.is_open:
        channel.queue_purge(QUEUE_GENERAR)
        channel.queue_purge(QUEUE_LISTO)
        connection.close()
    else:
        # La conexion pudo cerrarse dentro del test (simulacion de reinicio del
        # worker). Se usa una conexion nueva solo para limpiar la cola.
        cleanup_conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        cleanup_channel = cleanup_conn.channel()
        cleanup_channel.queue_purge(QUEUE_GENERAR)
        cleanup_channel.queue_purge(QUEUE_LISTO)
        cleanup_conn.close()


def _publicar(channel, payload: dict) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_GENERAR,
        body=json.dumps(payload).encode("utf-8"),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )


def _consumir_un_mensaje(engine, channel, *, timeout_s: float = 5.0):
    with Session(engine) as session:
        repository = _RepositoryAdapter(session)
        publisher = Publisher(channel, QUEUE_LISTO)
        consumer = Consumer(
            channel=channel,
            repository=repository,
            excel_builder=_ExcelBuilderAdapter,
            publisher=publisher,
        )
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=QUEUE_GENERAR, on_message_callback=consumer.procesar_mensaje)

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            channel.connection.process_data_events(time_limit=0.5)
        channel.stop_consuming()


def test_falla_transitoria_de_db_no_hace_ack_del_mensaje(engine, rabbit_channel):
    anuncio_id = f"anuncio-{uuid.uuid4()}"
    ahora = datetime.now(timezone.utc)
    payload = {
        "solicitud_id": str(uuid.uuid4()),
        "anuncio_id": anuncio_id,
        "fecha_desde": (ahora - timedelta(days=2)).isoformat(),
        "fecha_hasta": (ahora + timedelta(days=1)).isoformat(),
        "usuario_solicitante": "user-1",
    }
    _publicar(rabbit_channel, payload)

    with patch.object(
        repository_module,
        "anuncio_existe",
        side_effect=RuntimeError("conexion a la DB cortada"),
    ):
        _consumir_un_mensaje(engine, rabbit_channel)

    # El mensaje no se hizo ack: sigue "unacked" en este canal. Al reconectar
    # (simulando que el worker se reinicia tras la falla transitoria), RabbitMQ
    # lo redelivera, confirmando que no se perdio (FR-007 / Acceptance Scenario 1).
    rabbit_channel.connection.close()

    nueva_conexion = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    nuevo_canal = nueva_conexion.channel()
    method_frame, _, _ = nuevo_canal.basic_get(queue=QUEUE_GENERAR, auto_ack=True)
    nueva_conexion.close()

    assert method_frame is not None
