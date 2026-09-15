"""Integration tests: minio_client y persistencia contra MinIO real (docker-compose.test.yml)."""

from __future__ import annotations

import os

import pytest

from src.worker.storage.minio_client import crear_cliente_minio, asegurar_bucket

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
