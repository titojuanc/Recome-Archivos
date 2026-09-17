"""Repositorio de consulta de `ReporteAutorizacion` para el servicio de autorizacion."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.autorizacion import ReporteAutorizacion


def obtener_autorizacion(session: Session, solicitud_id: str) -> ReporteAutorizacion | None:
    """Devuelve el registro de autorizacion para `solicitud_id`, o `None` si no existe."""
    return session.get(ReporteAutorizacion, solicitud_id)
