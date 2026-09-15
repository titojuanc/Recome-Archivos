"""Publicacion del evento `reporte.listo` hacia RabbitMQ."""

from __future__ import annotations

import json

import pika

from src.worker.events.schemas import ReporteGenerado


class Publisher:
    """Publica `ReporteGenerado` en la cola configurada."""

    def __init__(self, channel: "pika.adapters.blocking_connection.BlockingChannel", queue: str):
        self._channel = channel
        self._queue = queue

    def publicar_reporte_listo(self, reporte: ReporteGenerado) -> None:
        payload = json.loads(reporte.model_dump_json())
        self._channel.basic_publish(
            exchange="",
            routing_key=self._queue,
            body=json.dumps(payload).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,  # persistente
            ),
        )
