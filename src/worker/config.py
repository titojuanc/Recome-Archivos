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
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool

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
            minio_endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
            minio_access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
            minio_secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
            minio_bucket=os.environ.get("MINIO_BUCKET", "reportes"),
            minio_secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
        )
