"""Control de idempotencia (User Story 3): evita reprocesar/duplicar solicitudes ante
fallos transitorios. Tabla propia de este repo, no compartida (data-model.md)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.idempotencia import EstadoIdempotencia, RegistroDeIdempotencia


def marcar_en_proceso(session: Session, solicitud_id: UUID) -> None:
    """Marca la solicitud como `en_proceso`, creando el registro si no existe."""

    registro = session.get(RegistroDeIdempotencia, solicitud_id)
    if registro is None:
        registro = RegistroDeIdempotencia(
            solicitud_id=solicitud_id,
            estado=EstadoIdempotencia.EN_PROCESO,
            creado_en=datetime.now(timezone.utc),
        )
        session.add(registro)
    else:
        registro.estado = EstadoIdempotencia.EN_PROCESO
    session.commit()


def marcar_completado(session: Session, solicitud_id: UUID) -> None:
    registro = session.get(RegistroDeIdempotencia, solicitud_id)
    if registro is None:
        raise ValueError(f"No existe registro de idempotencia para {solicitud_id}")
    registro.estado = EstadoIdempotencia.COMPLETADO
    registro.completado_en = datetime.now(timezone.utc)
    session.commit()


def marcar_fallido(session: Session, solicitud_id: UUID) -> None:
    registro = session.get(RegistroDeIdempotencia, solicitud_id)
    if registro is None:
        raise ValueError(f"No existe registro de idempotencia para {solicitud_id}")
    registro.estado = EstadoIdempotencia.FALLIDO
    session.commit()


def esta_completado(session: Session, solicitud_id: UUID) -> bool:
    registro = session.get(RegistroDeIdempotencia, solicitud_id)
    return registro is not None and registro.estado == EstadoIdempotencia.COMPLETADO
