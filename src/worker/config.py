"""Configuracion del worker via variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    rabbitmq_url: str
    database_url: str
    queue_reporte_generar: str
    queue_reporte_listo: str
    dead_letter_exchange: str
    max_concurrencia: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            rabbitmq_url=os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
            database_url=os.environ.get(
                "DATABASE_URL", "postgresql://reportes:reportes@localhost:5432/reportes"
            ),
            queue_reporte_generar=os.environ.get("QUEUE_REPORTE_GENERAR", "reporte.generar"),
            queue_reporte_listo=os.environ.get("QUEUE_REPORTE_LISTO", "reporte.listo"),
            dead_letter_exchange=os.environ.get(
                "DEAD_LETTER_EXCHANGE", "reporte.generar.dead-letter"
            ),
            max_concurrencia=int(os.environ.get("WORKER_MAX_CONCURRENCIA", "10")),
        )
