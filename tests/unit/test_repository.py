"""Unit tests: repository.obtener_eventos_anuncio().

Deben FALLAR hasta que exista src/worker/reportes/repository.py (TDD estricto).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.anuncio import Anuncio, Base

ANUNCIO_ID = "anuncio-123"
OTRO_ANUNCIO_ID = "anuncio-999"


@pytest.fixture()
def sesion():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ahora = datetime.now(timezone.utc)
        registros = [
            Anuncio(
                anuncio_id=ANUNCIO_ID,
                tipo_evento="impresion",
                timestamp=ahora - timedelta(days=5),
                usuario_id="user-1",
            ),
            Anuncio(
                anuncio_id=ANUNCIO_ID,
                tipo_evento="click",
                timestamp=ahora - timedelta(days=1),
                usuario_id="user-1",
            ),
            # Registro corrupto: timestamp NULL -> siempre incluido (Clarification #6)
            Anuncio(
                anuncio_id=ANUNCIO_ID,
                tipo_evento="impresion",
                timestamp=None,
                usuario_id=None,
            ),
            # Fuera de rango, mismo anuncio_id, con timestamp valido -> excluido
            Anuncio(
                anuncio_id=ANUNCIO_ID,
                tipo_evento="impresion",
                timestamp=ahora - timedelta(days=365),
                usuario_id="user-1",
            ),
            # Otro anuncio_id -> nunca debe aparecer
            Anuncio(
                anuncio_id=OTRO_ANUNCIO_ID,
                tipo_evento="click",
                timestamp=ahora - timedelta(days=1),
                usuario_id="user-2",
            ),
        ]
        session.add_all(registros)
        session.commit()
        yield session


def test_filtra_por_anuncio_id_y_rango_e_incluye_timestamps_nulos(sesion):
    from src.worker.reportes.repository import obtener_eventos_anuncio

    ahora = datetime.now(timezone.utc)
    desde = ahora - timedelta(days=10)
    hasta = ahora

    resultados = list(obtener_eventos_anuncio(sesion, ANUNCIO_ID, desde, hasta))

    anuncio_ids = {r.anuncio_id for r in resultados}
    assert anuncio_ids == {ANUNCIO_ID}

    # 2 dentro de rango + 1 con timestamp nulo = 3; el de hace 365 dias queda excluido
    assert len(resultados) == 3
    assert any(r.timestamp is None for r in resultados)


def test_no_incluye_registros_de_otro_anuncio_id(sesion):
    from src.worker.reportes.repository import obtener_eventos_anuncio

    ahora = datetime.now(timezone.utc)
    resultados = list(
        obtener_eventos_anuncio(sesion, ANUNCIO_ID, ahora - timedelta(days=10), ahora)
    )

    assert all(r.anuncio_id == ANUNCIO_ID for r in resultados)
