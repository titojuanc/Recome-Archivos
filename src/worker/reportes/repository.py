"""Acceso a la tabla compartida `anuncio` (ver data-model.md, Principio II)."""

from __future__ import annotations

from datetime import datetime
from typing import Iterator

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from src.models.anuncio import Anuncio


def anuncio_existe(session: Session, anuncio_id: str) -> bool:
    """Verifica si existe al menos un registro para `anuncio_id` (User Story 2)."""

    stmt = select(exists().where(Anuncio.anuncio_id == anuncio_id))
    return bool(session.execute(stmt).scalar())


def obtener_eventos_anuncio(
    session: Session,
    anuncio_id: str,
    fecha_desde: datetime,
    fecha_hasta: datetime,
) -> Iterator[Anuncio]:
    """Consulta eventos de `anuncio_id` en el rango [fecha_desde, fecha_hasta].

    Los registros con `timestamp IS NULL` (corruptos) se incluyen SIEMPRE, sin
    importar el rango solicitado (Clarification #6, data-model.md). La consulta
    usa un cursor server-side (yield_per) para soportar rangos sin limite maximo
    de forma incremental (FR-011).
    """

    stmt = select(Anuncio).where(
        Anuncio.anuncio_id == anuncio_id,
        or_(
            Anuncio.timestamp.between(fecha_desde, fecha_hasta),
            Anuncio.timestamp.is_(None),
        ),
    )

    for anuncio in session.execute(stmt).yield_per(1000).scalars():
        yield anuncio
