"""Unit tests: idempotencia/store.py marca estados en_proceso/completado/fallido.

Deben FALLAR hasta que exista src/worker/idempotencia/store.py (TDD estricto).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.anuncio import Base
from src.models.idempotencia import EstadoIdempotencia, RegistroDeIdempotencia


@pytest.fixture()
def sesion():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_marcar_en_proceso_crea_registro_nuevo(sesion):
    from src.worker.idempotencia.store import marcar_en_proceso

    solicitud_id = uuid4()
    marcar_en_proceso(sesion, solicitud_id)

    registro = sesion.get(RegistroDeIdempotencia, solicitud_id)
    assert registro is not None
    assert registro.estado == EstadoIdempotencia.EN_PROCESO


def test_marcar_completado_actualiza_estado_y_fecha(sesion):
    from src.worker.idempotencia.store import marcar_completado, marcar_en_proceso

    solicitud_id = uuid4()
    marcar_en_proceso(sesion, solicitud_id)
    marcar_completado(sesion, solicitud_id)

    registro = sesion.get(RegistroDeIdempotencia, solicitud_id)
    assert registro.estado == EstadoIdempotencia.COMPLETADO
    assert registro.completado_en is not None


def test_marcar_fallido_permite_reintentar(sesion):
    from src.worker.idempotencia.store import marcar_en_proceso, marcar_fallido

    solicitud_id = uuid4()
    marcar_en_proceso(sesion, solicitud_id)
    marcar_fallido(sesion, solicitud_id)

    registro = sesion.get(RegistroDeIdempotencia, solicitud_id)
    assert registro.estado == EstadoIdempotencia.FALLIDO

    # Reintento tras falla: debe poder volver a marcarse en_proceso
    marcar_en_proceso(sesion, solicitud_id)
    registro = sesion.get(RegistroDeIdempotencia, solicitud_id)
    assert registro.estado == EstadoIdempotencia.EN_PROCESO


def test_ya_completado_no_debe_reprocesarse(sesion):
    from src.worker.idempotencia.store import esta_completado, marcar_completado, marcar_en_proceso

    solicitud_id = uuid4()
    marcar_en_proceso(sesion, solicitud_id)
    marcar_completado(sesion, solicitud_id)

    assert esta_completado(sesion, solicitud_id) is True


def test_solicitud_nueva_no_esta_completada(sesion):
    from src.worker.idempotencia.store import esta_completado

    assert esta_completado(sesion, uuid4()) is False
