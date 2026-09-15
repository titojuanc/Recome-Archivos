"""Integration tests: comportamiento de ack/nack del consumer contra RabbitMQ real."""

from __future__ import annotations

import json
import os
import time
import uuid
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

QUEUE_GENERAR = "test.rabbitmq.reporte.generar"
QUEUE_LISTO = "test.rabbitmq.reporte.listo"
DEAD_LETTER_QUEUE = "test.rabbitmq.dead-letter"


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


def test_mensaje_valido_se_hace_ack_y_no_queda_en_la_cola(engine, rabbit_channel):
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
    _consumir_un_mensaje(engine, rabbit_channel)

    # El mensaje ya fue ack-eado: la cola de reporte.generar debe estar vacia.
    method_frame, _, _ = rabbit_channel.basic_get(queue=QUEUE_GENERAR, auto_ack=False)
    assert method_frame is None


def test_mensaje_invalido_sin_anuncio_id_se_rechaza_sin_publicar_listo(engine, rabbit_channel):
    payload = {
        "solicitud_id": str(uuid.uuid4()),
        # anuncio_id omitido intencionalmente
        "fecha_desde": "2020-01-01T00:00:00Z",
        "fecha_hasta": "2030-01-01T00:00:00Z",
        "usuario_solicitante": "user-1",
    }
    _publicar(rabbit_channel, payload)
    _consumir_un_mensaje(engine, rabbit_channel)

    method_frame, _, body = rabbit_channel.basic_get(queue=QUEUE_LISTO, auto_ack=True)
    assert body is None
