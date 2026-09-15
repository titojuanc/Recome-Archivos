"""Wrapper del SDK oficial de MinIO: conexion y verificacion/creacion de bucket."""

from __future__ import annotations

from minio import Minio
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule
from minio.commonconfig import ENABLED, Filter


def crear_cliente_minio(
    *, endpoint: str, access_key: str, secret_key: str, secure: bool = False
) -> Minio:
    """Crea un cliente MinIO configurado a partir de los parametros dados."""
    return Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


def asegurar_bucket(client: Minio, bucket: str) -> None:
    """Verifica que el bucket exista y lo crea si no es el caso."""
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def aplicar_lifecycle_rules(client: Minio, bucket: str, reglas: dict) -> None:
    """Aplica una lifecycle rule de expiracion nativa de MinIO sobre `bucket`.

    `reglas` sigue el formato de `infra/minio/lifecycle-rules.json`:
    `{"prefijo": str, "dias_retencion": int}`. No hay logica propia de limpieza
    (Clarification #2): la eliminacion la ejecuta MinIO de forma nativa en background.
    """
    config = LifecycleConfig(
        [
            Rule(
                ENABLED,
                rule_filter=Filter(prefix=reglas["prefijo"]),
                rule_id="retencion-reportes",
                expiration=Expiration(days=reglas["dias_retencion"]),
            ),
        ],
    )
    client.set_bucket_lifecycle(bucket, config)

