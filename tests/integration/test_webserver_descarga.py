"""Integration tests: flujo completo de descarga a traves de Nginx + auth-service +
MinIO + PostgreSQL reales (docker-compose.test.yml)."""

from __future__ import annotations

import io
import os
import time
import uuid

import httpx
import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.anuncio import Base
from src.models.autorizacion import ReporteAutorizacion
from src.worker.reportes.autorizacion_repository import registrar_autorizacion
from src.worker.storage.minio_client import (
    aplicar_politica_lectura_interna,
    asegurar_bucket,
    crear_cliente_minio,
)
from src.worker.storage.persistencia import subir_reporte

NGINX_BASE_URL = os.environ.get("TEST_NGINX_URL", "http://localhost:8080")
JWT_SECRET = os.environ.get("TEST_JWT_SECRET", "testing-secret")
MINIO_ENDPOINT = os.environ.get("TEST_MINIO_ENDPOINT", "localhost:9002")
MINIO_ACCESS_KEY = os.environ.get("TEST_MINIO_ACCESS_KEY", "reportes-test")
MINIO_SECRET_KEY = os.environ.get("TEST_MINIO_SECRET_KEY", "reportes-test-secret")
MINIO_BUCKET = os.environ.get("TEST_MINIO_BUCKET", "reportes-test")
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://reportes:reportes@localhost:5433/reportes"
)


def _token(sub: str, exp_delta: int = 3600) -> str:
    return jwt.encode(
        {"sub": sub, "exp": int(time.time()) + exp_delta}, JWT_SECRET, algorithm="HS256"
    )


@pytest.fixture(scope="module")
def minio_cliente():
    client = crear_cliente_minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    asegurar_bucket(client, MINIO_BUCKET)
    aplicar_politica_lectura_interna(client, MINIO_BUCKET)
    return client


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    return engine


def _crear_reporte_autorizado(minio_cliente, db_engine, *, usuario: str, contenido: bytes):
    anuncio_id = f"anuncio-{uuid.uuid4()}"
    solicitud_id = str(uuid.uuid4())
    referencia = subir_reporte(
        anuncio_id, solicitud_id, io.BytesIO(contenido), client=minio_cliente, bucket=MINIO_BUCKET
    )
    with Session(db_engine) as session:
        registrar_autorizacion(
            session,
            solicitud_id=solicitud_id,
            anuncio_id=anuncio_id,
            usuario_solicitante=usuario,
            bucket=referencia.bucket,
            key=referencia.key,
        )
    return solicitud_id


def test_descarga_autorizada_devuelve_contenido_identico(minio_cliente, db_engine):
    contenido = b"contenido-us1-scenario-1"
    solicitud_id = _crear_reporte_autorizado(
        minio_cliente, db_engine, usuario="usuario-1", contenido=contenido
    )

    resp = httpx.get(
        f"{NGINX_BASE_URL}/reportes/{solicitud_id}",
        headers={"Authorization": f"Bearer {_token('usuario-1')}"},
    )

    assert resp.status_code == 200
    assert resp.content == contenido


def test_descarga_autorizada_repetida_sigue_funcionando(minio_cliente, db_engine):
    contenido = b"contenido-us1-scenario-2"
    solicitud_id = _crear_reporte_autorizado(
        minio_cliente, db_engine, usuario="usuario-1", contenido=contenido
    )

    resp1 = httpx.get(
        f"{NGINX_BASE_URL}/reportes/{solicitud_id}",
        headers={"Authorization": f"Bearer {_token('usuario-1')}"},
    )
    resp2 = httpx.get(
        f"{NGINX_BASE_URL}/reportes/{solicitud_id}",
        headers={"Authorization": f"Bearer {_token('usuario-1')}"},
    )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.content == resp2.content == contenido


def test_descarga_sin_credenciales_devuelve_401_sin_contenido(minio_cliente, db_engine):
    contenido = b"contenido-us2-sin-credenciales"
    solicitud_id = _crear_reporte_autorizado(
        minio_cliente, db_engine, usuario="usuario-1", contenido=contenido
    )

    resp = httpx.get(f"{NGINX_BASE_URL}/reportes/{solicitud_id}")

    assert resp.status_code == 401
    assert contenido not in resp.content


def test_descarga_con_usuario_no_autorizado_devuelve_403_sin_contenido(minio_cliente, db_engine):
    contenido = b"contenido-us2-usuario-incorrecto"
    solicitud_id = _crear_reporte_autorizado(
        minio_cliente, db_engine, usuario="usuario-1", contenido=contenido
    )

    resp = httpx.get(
        f"{NGINX_BASE_URL}/reportes/{solicitud_id}",
        headers={"Authorization": f"Bearer {_token('usuario-2')}"},
    )

    assert resp.status_code == 403
    assert contenido not in resp.content


def test_descarga_con_jwt_expirado_devuelve_401(minio_cliente, db_engine):
    contenido = b"contenido-us2-jwt-expirado"
    solicitud_id = _crear_reporte_autorizado(
        minio_cliente, db_engine, usuario="usuario-1", contenido=contenido
    )

    resp = httpx.get(
        f"{NGINX_BASE_URL}/reportes/{solicitud_id}",
        headers={"Authorization": f"Bearer {_token('usuario-1', exp_delta=-10)}"},
    )

    assert resp.status_code == 401
    assert contenido not in resp.content


def test_descarga_solicitud_id_inexistente_devuelve_404(minio_cliente, db_engine):
    resp = httpx.get(
        f"{NGINX_BASE_URL}/reportes/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {_token('usuario-1')}"},
    )

    assert resp.status_code == 404


def test_descarga_objeto_eliminado_de_minio_no_expone_error_nativo(minio_cliente, db_engine):
    contenido = b"contenido-us3-objeto-eliminado"
    solicitud_id = _crear_reporte_autorizado(
        minio_cliente, db_engine, usuario="usuario-1", contenido=contenido
    )
    with Session(db_engine) as session:
        autorizacion = session.get(ReporteAutorizacion, solicitud_id)
        bucket, key = autorizacion.bucket, autorizacion.key
    minio_cliente.remove_object(bucket, key)

    resp = httpx.get(
        f"{NGINX_BASE_URL}/reportes/{solicitud_id}",
        headers={"Authorization": f"Bearer {_token('usuario-1')}"},
    )

    assert resp.status_code in (404, 502)
    assert b"<?xml" not in resp.content
    assert b"NoSuchKey" not in resp.content
