"""Modelo de la tabla compartida `anuncio` (Principio II de la constitution: unica
excepcion documentada de aislamiento de datos, compartida con api-general).

El schema exacto y autoritativo vive documentado en api-general; lo aqui descrito es
la interpretacion de trabajo de este repo (ver data-model.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Anuncio(Base):
    """Registro individual de un evento de interaccion (impresion o click)."""

    __tablename__ = "anuncio"
    __table_args__ = (
        CheckConstraint(
            "tipo_evento IN ('impresion', 'click')", name="ck_anuncio_tipo_evento"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    anuncio_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tipo_evento: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usuario_id: Mapped[str | None] = mapped_column(String, nullable=True)
