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


def obtener_eventos_multiples_anuncios(
    session: Session,
    anuncio_ids: list[str],
    fecha_desde: datetime,
    fecha_hasta: datetime,
) -> Iterator[Anuncio]:
    """Igual que `obtener_eventos_anuncio` pero para VARIOS anuncios a la vez
    (reporte consolidado de toda la actividad de un vendedor).

    Ordena por `anuncio_id` (y luego `timestamp`) para que, al volcar los
    eventos al Excel, los de un mismo anuncio queden contiguos/agrupados
    (separación prolija por anuncio dentro de cada hoja).
    """

    stmt = (
        select(Anuncio)
        .where(
            Anuncio.anuncio_id.in_(anuncio_ids),
            or_(
                Anuncio.timestamp.between(fecha_desde, fecha_hasta),
                Anuncio.timestamp.is_(None),
            ),
        )
        .order_by(Anuncio.anuncio_id, Anuncio.timestamp)
    )

    for anuncio in session.execute(stmt).yield_per(1000).scalars():
        yield anuncio
