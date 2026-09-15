"""Integration tests: flujo end-to-end reporte.generar -> Excel -> reporte.listo.

Requiere RabbitMQ + PostgreSQL reales (ver docker-compose.test.yml, puertos 5673/5433).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pika
import pytest
from sqlalchemy import create_engine, text
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

QUEUE_GENERAR = "test.reporte.generar"
QUEUE_LISTO = "test.reporte.listo"


class _RepositoryAdapter:
    def __init__(self, session: Session):
        self._session = session

    def obtener_eventos_anuncio(self, anuncio_id, fecha_desde, fecha_hasta):
        return repository_module.obtener_eventos_anuncio(
            self._session, anuncio_id, fecha_desde, fecha_hasta
        )


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
    channel.queue_purge(QUEUE_GENERAR)
    channel.queue_purge(QUEUE_LISTO)
    connection.close()


def _insertar_evento(engine, anuncio_id, tipo_evento, timestamp, usuario_id="user-1"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO anuncio (id, anuncio_id, tipo_evento, timestamp, usuario_id) "
                "VALUES (:id, :anuncio_id, :tipo_evento, :timestamp, :usuario_id)"
            ),
            {
                "id": str(uuid.uuid4()),
                "anuncio_id": anuncio_id,
                "tipo_evento": tipo_evento,
                "timestamp": timestamp,
                "usuario_id": usuario_id,
            },
        )


def _publicar_solicitud(channel, payload: dict) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_GENERAR,
        body=json.dumps(payload).encode("utf-8"),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )


def _consumir_un_mensaje(engine, channel, *, timeout_s: float = 5.0):
    """Consume exactamente un mensaje de QUEUE_GENERAR usando el Consumer real."""

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


def _leer_mensaje_listo(channel) -> dict | None:
    method, properties, body = channel.basic_get(queue=QUEUE_LISTO, auto_ack=True)
    if body is None:
        return None
    return json.loads(body)


def test_flujo_end_to_end_con_datos_publica_reporte_listo_generado(engine, rabbit_channel):
    anuncio_id = f"anuncio-{uuid.uuid4()}"
    ahora = datetime.now(timezone.utc)
    _insertar_evento(engine, anuncio_id, "impresion", ahora - timedelta(days=1))
    _insertar_evento(engine, anuncio_id, "click", ahora - timedelta(hours=12))

    payload = {
        "solicitud_id": str(uuid.uuid4()),
        "anuncio_id": anuncio_id,
        "fecha_desde": (ahora - timedelta(days=2)).isoformat(),
        "fecha_hasta": (ahora + timedelta(days=1)).isoformat(),
        "usuario_solicitante": "user-1",
    }
    _publicar_solicitud(rabbit_channel, payload)
    _consumir_un_mensaje(engine, rabbit_channel)

    resultado = _leer_mensaje_listo(rabbit_channel)

    assert resultado is not None
    assert resultado["solicitud_id"] == payload["solicitud_id"]
    assert resultado["estado"] == "generado"


def test_flujo_end_to_end_sin_datos_publica_reporte_listo_vacio(engine, rabbit_channel):
    anuncio_id = f"anuncio-{uuid.uuid4()}"
    ahora = datetime.now(timezone.utc)

    payload = {
        "solicitud_id": str(uuid.uuid4()),
        "anuncio_id": anuncio_id,
        "fecha_desde": (ahora - timedelta(days=2)).isoformat(),
        "fecha_hasta": (ahora + timedelta(days=1)).isoformat(),
        "usuario_solicitante": "user-1",
    }
    _publicar_solicitud(rabbit_channel, payload)
    _consumir_un_mensaje(engine, rabbit_channel)

    resultado = _leer_mensaje_listo(rabbit_channel)

    assert resultado is not None
    assert resultado["estado"] == "vacio"
