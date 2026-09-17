"""Escritura de `ReporteAutorizacion` (usado por el worker tras subir_reporte exitoso)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.autorizacion import ReporteAutorizacion


def registrar_autorizacion(
    session: Session,
    *,
    solicitud_id,
    anuncio_id: str,
    usuario_solicitante: str,
    bucket: str,
    key: str,
) -> None:
    """Inserta el registro de autorizacion para `solicitud_id` y hace commit."""
    session.add(
        ReporteAutorizacion(
            solicitud_id=str(solicitud_id),
            anuncio_id=anuncio_id,
            usuario_solicitante=usuario_solicitante,
            bucket=bucket,
            key=key,
        )
    )
    session.commit()
