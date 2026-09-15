"""Integration tests: minio_client y persistencia contra MinIO real (docker-compose.test.yml)."""

from __future__ import annotations

import io
import os
import uuid

import pytest

from src.worker.storage.key_builder import construir_key
from src.worker.storage.minio_client import crear_cliente_minio, asegurar_bucket
from src.worker.storage.persistencia import FalloDePersistencia, subir_reporte

MINIO_ENDPOINT = os.environ.get("TEST_MINIO_ENDPOINT", "localhost:9002")
MINIO_ACCESS_KEY = os.environ.get("TEST_MINIO_ACCESS_KEY", "reportes-test")
MINIO_SECRET_KEY = os.environ.get("TEST_MINIO_SECRET_KEY", "reportes-test-secret")
MINIO_BUCKET = os.environ.get("TEST_MINIO_BUCKET", "reportes-test")


@pytest.fixture()
def cliente():
    client = crear_cliente_minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    asegurar_bucket(client, MINIO_BUCKET)
    return client


def test_conexion_y_bucket_se_crea_si_no_existe(cliente):
    assert cliente.bucket_exists(MINIO_BUCKET)


def test_subir_reporte_produce_key_esperada(cliente):
    anuncio_id = f"anuncio-{uuid.uuid4()}"
    solicitud_id = f"solicitud-{uuid.uuid4()}"
    contenido = b"contenido del reporte de prueba"

    referencia = subir_reporte(
        anuncio_id, solicitud_id, io.BytesIO(contenido), client=cliente, bucket=MINIO_BUCKET
    )

    assert referencia.key == construir_key(anuncio_id, solicitud_id)
    assert referencia.bucket == MINIO_BUCKET


def test_subir_reporte_contenido_recuperado_es_identico(cliente):
    anuncio_id = f"anuncio-{uuid.uuid4()}"
    solicitud_id = f"solicitud-{uuid.uuid4()}"
    contenido = b"contenido byte a byte para verificar integridad"

    referencia = subir_reporte(
        anuncio_id, solicitud_id, io.BytesIO(contenido), client=cliente, bucket=MINIO_BUCKET
    )

    respuesta = cliente.get_object(referencia.bucket, referencia.key)
    try:
        recuperado = respuesta.read()
    finally:
        respuesta.close()
        respuesta.release_conn()

    assert recuperado == contenido


def test_subir_reporte_devuelve_referencia_valida(cliente):
    anuncio_id = f"anuncio-{uuid.uuid4()}"
    solicitud_id = f"solicitud-{uuid.uuid4()}"
    contenido = b"otro contenido de prueba"

    referencia = subir_reporte(
        anuncio_id, solicitud_id, io.BytesIO(contenido), client=cliente, bucket=MINIO_BUCKET
    )

    assert referencia.bucket
    assert referencia.key
    assert referencia.etag

    import json
    from pathlib import Path

    from jsonschema import validate

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "specs"
        / "002-minio-storage"
        / "contracts"
        / "referencia_archivo.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    validate(
        instance={
            "bucket": referencia.bucket,
            "key": referencia.key,
            "etag": referencia.etag,
        },
        schema=schema,
    )


def test_subir_reporte_falla_si_etag_no_coincide_con_checksum_local(cliente, monkeypatch):
    import src.worker.storage.persistencia as persistencia_module

    monkeypatch.setattr(
        persistencia_module, "calcular_checksum", lambda _archivo: "checksum-forzado-invalido"
    )

    anuncio_id = f"anuncio-{uuid.uuid4()}"
    solicitud_id = f"solicitud-{uuid.uuid4()}"
    contenido = b"contenido para probar fallo de integridad"

    with pytest.raises(FalloDePersistencia):
        subir_reporte(
            anuncio_id,
            solicitud_id,
            io.BytesIO(contenido),
            client=cliente,
            bucket=MINIO_BUCKET,
        )
