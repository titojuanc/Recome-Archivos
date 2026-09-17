"""Configuracion del microservicio de autorizacion via variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    jwt_secret: str
    database_url: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            jwt_secret=os.environ.get("JWT_SECRET", "testing-secret"),
            database_url=os.environ.get(
                "DATABASE_URL", "postgresql+psycopg://reportes:reportes@localhost:5432/reportes"
            ),
        )
