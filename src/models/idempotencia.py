"""Modelo de la tabla propia de idempotencia (NO compartida; ver data-model.md).

Propiedad exclusiva de este repo; no amplia la excepcion de aislamiento de datos del
Principio II de la constitution.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.anuncio import Base


class EstadoIdempotencia(str, Enum):
    EN_PROCESO = "en_proceso"
    COMPLETADO = "completado"
    FALLIDO = "fallido"


class RegistroDeIdempotencia(Base):
    """Controla el procesamiento unico por `solicitud_id`."""

    __tablename__ = "registro_idempotencia"

    solicitud_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    estado: Mapped[str] = mapped_column(nullable=False, default=EstadoIdempotencia.EN_PROCESO)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
