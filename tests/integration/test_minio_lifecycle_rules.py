"""Integration tests: lifecycle rules nativas de MinIO para retencion (US3).

Nota: la expiracion real de un objeto por una lifecycle rule ocurre en background
(orden de horas/dias en un MinIO real), por lo que estos tests validan que la regla
queda correctamente configurada y aplicada al bucket (Acceptance Scenario 1) y que un
objeto subido sigue intacto inmediatamente despues de configurar la regla (Acceptance
Scenario 2), en lugar de esperar el periodo de expiracion completo dentro del test.
"""

from __future__ import annotations

import io
import json
import os
import uuid
from pathlib import Path

import pytest

from src.worker.storage.minio_client import (
    aplicar_lifecycle_rules,
    asegurar_bucket,
    crear_cliente_minio,
)

MINIO_ENDPOINT = os.environ.get("TEST_MINIO_ENDPOINT", "localhost:9002")
MINIO_ACCESS_KEY = os.environ.get("TEST_MINIO_ACCESS_KEY", "reportes-test")
MINIO_SECRET_KEY = os.environ.get("TEST_MINIO_SECRET_KEY", "reportes-test-secret")
MINIO_BUCKET = os.environ.get("TEST_MINIO_BUCKET", "reportes-test")

LIFECYCLE_RULES_PATH = (
    Path(__file__).resolve().parents[2] / "infra" / "minio" / "lifecycle-rules.json"
)


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


def test_lifecycle_rule_se_configura_correctamente_sobre_el_bucket(cliente):
    reglas = json.loads(LIFECYCLE_RULES_PATH.read_text())

    aplicar_lifecycle_rules(cliente, MINIO_BUCKET, reglas)

    config = cliente.get_bucket_lifecycle(MINIO_BUCKET)
    regla = config.rules[0]
    assert regla.rule_filter.prefix == reglas["prefijo"]
    assert regla.expiration.days == reglas["dias_retencion"]


def test_objeto_reciente_permanece_intacto_tras_aplicar_lifecycle_rule(cliente):
    reglas = json.loads(LIFECYCLE_RULES_PATH.read_text())
    aplicar_lifecycle_rules(cliente, MINIO_BUCKET, reglas)

    key = f"reportes/lifecycle-test-{uuid.uuid4()}.xlsx"
    contenido = b"objeto reciente que no debe ser eliminado de inmediato"
    cliente.put_object(MINIO_BUCKET, key, io.BytesIO(contenido), length=len(contenido))

    # Inmediatamente despues de configurar la regla, el objeto reciente debe
    # seguir siendo accesible (la expiracion opera sobre la antiguedad del objeto,
    # no de forma retroactiva instantanea).
    stat = cliente.stat_object(MINIO_BUCKET, key)
    assert stat.size == len(contenido)
