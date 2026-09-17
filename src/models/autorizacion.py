"""Modelo de la tabla propia `reporte_autorizacion` (NO compartida; ver data-model.md).

Propiedad exclusiva de este repo; asocia un reporte generado (001-worker-reportes /
002-minio-storage) con el usuario autorizado a descargarlo (003-webserver-archivos).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.anuncio import Base


class ReporteAutorizacion(Base):
    """Asocia `solicitud_id` -> `usuario_solicitante` autorizado a descargar el reporte."""

    __tablename__ = "reporte_autorizacion"

    solicitud_id: Mapped[str] = mapped_column(String, primary_key=True)
    anuncio_id: Mapped[str] = mapped_column(String, nullable=False)
    usuario_solicitante: Mapped[str] = mapped_column(String, nullable=False)
    bucket: Mapped[str] = mapped_column(String, nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
