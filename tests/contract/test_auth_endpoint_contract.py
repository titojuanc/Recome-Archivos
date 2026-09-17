"""Contract tests: endpoint GET /auth del microservicio de autorizacion.

Valida contra specs/003-webserver-archivos/contracts/auth_endpoint.schema.json
(estructura logica de request/responses), usando el TestClient de FastAPI (sin Nginx
real; ver tests/integration/test_webserver_descarga.py para el flujo completo con Nginx).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from jsonschema import validate
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models.anuncio import Base
from src.models.autorizacion import ReporteAutorizacion

SECRET = "testing-secret"

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "003-webserver-archivos"
    / "contracts"
    / "auth_endpoint.schema.json"
)


def _token(sub="usuario-1", exp_delta=3600):
    return jwt.encode({"sub": sub, "exp": int(time.time()) + exp_delta}, SECRET, algorithm="HS256")


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    monkeypatch.setenv("JWT_SECRET", SECRET)

    from src.webserver.auth_service import main as main_module

    monkeypatch.setattr(main_module, "SessionLocal", SessionLocal)

    with SessionLocal() as session:
        yield TestClient(main_module.app), session


def test_auth_endpoint_200_con_jwt_valido_y_autorizado(client):
    test_client, session = client
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

    resp = test_client.get(
        "/auth",
        headers={
            "Authorization": f"Bearer {_token(sub='usuario-1')}",
            "X-Solicitud-Id": solicitud_id,
        },
    )

    assert resp.status_code == 200
    assert resp.headers["X-Bucket"] == "reportes-test"
    assert resp.headers["X-Object-Key"] == f"reportes/anuncio-123/{solicitud_id}.xlsx"

    schema = json.loads(SCHEMA_PATH.read_text())
    validate(
        instance={
            "request": {
                "Authorization": f"Bearer {_token(sub='usuario-1')}",
                "X-Solicitud-Id": solicitud_id,
            },
            "responses": {"200": {}},
        },
        schema=schema,
    )
