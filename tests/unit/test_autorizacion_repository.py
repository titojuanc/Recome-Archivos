"""Unit tests: autorizacion_repository.obtener_autorizacion (T007)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.anuncio import Base
from src.models.autorizacion import ReporteAutorizacion
from src.webserver.auth_service.autorizacion_repository import obtener_autorizacion


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_obtener_autorizacion_devuelve_registro_existente(session):
    solicitud_id = str(uuid.uuid4())
    session.add(
        ReporteAutorizacion(
            solicitud_id=solicitud_id,
            anuncio_id="anuncio-123",
            usuario_solicitante="usuario-1",
            bucket="reportes-test",
            key=f"reportes/anuncio-123/{solicitud_id}.xlsx",
        )
    )
    session.commit()

    resultado = obtener_autorizacion(session, solicitud_id)

    assert resultado is not None
    assert resultado.usuario_solicitante == "usuario-1"
    assert resultado.bucket == "reportes-test"


def test_obtener_autorizacion_devuelve_none_si_no_existe(session):
    resultado = obtener_autorizacion(session, str(uuid.uuid4()))
    assert resultado is None
