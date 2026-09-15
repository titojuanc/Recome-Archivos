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
from src.worker.reportes import repository as repository_module

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

    with Session(engine) as session:
        repository = _RepositoryAdapter(session)
        publisher = Publisher(channel, config.queue_reporte_listo)
        consumer = Consumer(
            channel=channel,
            repository=repository,
            excel_builder=type("_EB", (), {"construir_reporte": staticmethod(construir_reporte)}),
            publisher=publisher,
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
