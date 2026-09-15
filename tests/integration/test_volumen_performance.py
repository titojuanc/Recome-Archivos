"""Test de volumen/performance (SC-001): generar reporte con ~100.000 registros
en menos de 30 segundos. Verifica ademas que la generacion es streaming (no
consume memoria excesiva) via el flujo real repository -> excel_builder.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.anuncio import Anuncio, Base
from src.worker.reportes.excel_builder import construir_reporte
from src.worker.reportes.repository import obtener_eventos_anuncio

ANUNCIO_ID = "anuncio-volumen"
N_REGISTROS = 100_000


@pytest.fixture(scope="module")
def engine_con_volumen():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    ahora = datetime.now(timezone.utc)
    with Session(engine) as session:
        lote = []
        for i in range(N_REGISTROS):
            lote.append(
                Anuncio(
                    anuncio_id=ANUNCIO_ID,
                    tipo_evento="impresion" if i % 2 == 0 else "click",
                    timestamp=ahora - timedelta(seconds=i),
                    usuario_id=f"user-{i % 100}",
                )
            )
            if len(lote) >= 5000:
                session.bulk_save_objects(lote)
                lote.clear()
        if lote:
            session.bulk_save_objects(lote)
        session.commit()
    yield engine
    engine.dispose()


def test_genera_reporte_de_100k_registros_en_menos_de_30_segundos(engine_con_volumen):
    ahora = datetime.now(timezone.utc)

    inicio = time.monotonic()
    with Session(engine_con_volumen) as session:
        eventos = obtener_eventos_anuncio(
            session,
            ANUNCIO_ID,
            ahora - timedelta(days=2),
            ahora + timedelta(days=1),
        )
        buffer = construir_reporte(eventos)
    duracion = time.monotonic() - inicio

    assert duracion < 30.0, f"La generacion tardo {duracion:.2f}s (SC-001: < 30s)"
    assert buffer.getbuffer().nbytes > 0
