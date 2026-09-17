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


def test_auth_endpoint_401_sin_authorization_header(client):
    test_client, _session = client
    resp = test_client.get("/auth", headers={"X-Solicitud-Id": str(uuid.uuid4())})
    assert resp.status_code == 401


def test_auth_endpoint_401_con_jwt_invalido_o_expirado(client):
    test_client, _session = client
    token_expirado = _token(sub="usuario-1", exp_delta=-10)
    resp = test_client.get(
        "/auth",
        headers={
            "Authorization": f"Bearer {token_expirado}",
            "X-Solicitud-Id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 401

    resp2 = test_client.get(
        "/auth",
        headers={
            "Authorization": "Bearer token-mal-formado",
            "X-Solicitud-Id": str(uuid.uuid4()),
        },
    )
    assert resp2.status_code == 401


def test_auth_endpoint_403_con_usuario_distinto_al_autorizado(client):
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
            "Authorization": f"Bearer {_token(sub='usuario-2')}",
            "X-Solicitud-Id": solicitud_id,
        },
    )
    assert resp.status_code == 403


def test_auth_endpoint_404_solicitud_id_sin_autorizacion(client):
    test_client, _session = client
    resp = test_client.get(
        "/auth",
        headers={
            "Authorization": f"Bearer {_token(sub='usuario-1')}",
            "X-Solicitud-Id": str(uuid.uuid4()),
        },
    )
    # El endpoint expone el caso "no encontrado" como 403 + X-Auth-Reason=not_found
    # (auth_request de Nginx solo soporta nativamente 200/401/403); Nginx traduce
    # esto a un 404 real hacia el cliente final (ver infra/nginx/nginx.conf).
    assert resp.status_code == 403
    assert resp.headers["X-Auth-Reason"] == "not_found"
