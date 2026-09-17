"""Entry point del worker: conecta RabbitMQ + PostgreSQL y arranca el loop de consumo."""

from __future__ import annotations

import functools
import logging

import pika
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.worker.config import Config
from src.worker.events.consumer import Consumer
from src.worker.events.publisher import Publisher
from src.worker.idempotencia import store as idempotencia_store
from src.worker.reportes import autorizacion_repository as autorizacion_repository_module
from src.worker.reportes import repository as repository_module
from src.worker.storage import minio_client as minio_client_module
from src.worker.storage import persistencia as persistencia_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger("worker.main")


class _RepositoryAdapter:
    """Adapta el modulo repository (funcion pura) a la interfaz esperada por service."""

    def __init__(self, session: Session):
        self._session = session

    def obtener_eventos_anuncio(self, anuncio_id, fecha_desde, fecha_hasta):
        return repository_module.obtener_eventos_anuncio(
            self._session, anuncio_id, fecha_desde, fecha_hasta
        )

    def anuncio_existe(self, anuncio_id):
        return repository_module.anuncio_existe(self._session, anuncio_id)


class _IdempotenciaAdapter:
    """Adapta el modulo idempotencia/store.py a la interfaz esperada por service."""

    def __init__(self, session: Session):
        self._session = session

    def esta_completado(self, solicitud_id):
        return idempotencia_store.esta_completado(self._session, solicitud_id)

    def marcar_en_proceso(self, solicitud_id):
        idempotencia_store.marcar_en_proceso(self._session, solicitud_id)

    def marcar_completado(self, solicitud_id):
        idempotencia_store.marcar_completado(self._session, solicitud_id)

    def marcar_fallido(self, solicitud_id):
        idempotencia_store.marcar_fallido(self._session, solicitud_id)


class _PersistenciaAdapter:
    """Adapta storage.persistencia (funciones puras) a la interfaz esperada por service."""

    def __init__(self, client, bucket: str):
        self._client = client
        self._bucket = bucket

    def subir_reporte(self, anuncio_id, solicitud_id, archivo):
        return persistencia_module.subir_reporte(
            anuncio_id, solicitud_id, archivo, client=self._client, bucket=self._bucket
        )


class _AutorizacionRepositoryAdapter:
    """Adapta autorizacion_repository (funcion pura) a la interfaz esperada por service."""

    def __init__(self, session: Session):
        self._session = session

    def registrar_autorizacion(self, *, solicitud_id, anuncio_id, usuario_solicitante, bucket, key):
        autorizacion_repository_module.registrar_autorizacion(
            self._session,
            solicitud_id=solicitud_id,
            anuncio_id=anuncio_id,
            usuario_solicitante=usuario_solicitante,
            bucket=bucket,
            key=key,
        )


def main() -> None:
    config = Config.from_env()
    logger.info(
        "Iniciando worker de reportes (queue=%s, dead_letter=%s, max_concurrencia=%s)",
        config.queue_reporte_generar,
        config.dead_letter_exchange,
        config.max_concurrencia,
    )

    engine = create_engine(config.database_url)
    connection = pika.BlockingConnection(pika.URLParameters(config.rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue=config.queue_reporte_generar, durable=True)
    channel.queue_declare(queue=config.queue_reporte_listo, durable=True)

    from src.worker.reportes.excel_builder import construir_reporte

    minio_cliente = minio_client_module.crear_cliente_minio(
        endpoint=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        secure=config.minio_secure,
    )
    minio_client_module.asegurar_bucket(minio_cliente, config.minio_bucket)

    with Session(engine) as session:
        repository = _RepositoryAdapter(session)
        publisher = Publisher(channel, config.queue_reporte_listo)
        idempotencia = _IdempotenciaAdapter(session)
        persistencia = _PersistenciaAdapter(minio_cliente, config.minio_bucket)
        autorizacion_repository = _AutorizacionRepositoryAdapter(session)
        consumer = Consumer(
            channel=channel,
            repository=repository,
            excel_builder=type("_EB", (), {"construir_reporte": staticmethod(construir_reporte)}),
            publisher=publisher,
            idempotencia=idempotencia,
            persistencia=persistencia,
            autorizacion_repository=autorizacion_repository,
        )

        channel.basic_qos(prefetch_count=config.max_concurrencia)
        channel.basic_consume(
            queue=config.queue_reporte_generar,
            on_message_callback=consumer.procesar_mensaje,
        )

        logger.info("Worker listo, esperando mensajes en %s", config.queue_reporte_generar)
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
        finally:
            connection.close()


if __name__ == "__main__":
    main()
