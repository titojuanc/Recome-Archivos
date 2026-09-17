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


def aplicar_politica_lectura_interna(client: Minio, bucket: str) -> None:
    """Permite lectura anonima de objetos del bucket (requerido por el proxy directo
    de Nginx en `003-webserver-archivos`, que no firma solicitudes S3/SigV4).

    Esta politica es segura porque MinIO nunca se expone directamente al cliente
    final: solo el Nginx de este repo puede alcanzarlo en la red interna, y es ese
    Nginx quien exige autorizacion (via `auth_request`) antes de proxear cualquier
    solicitud hacia MinIO (FR-001 a FR-003 de 003-webserver-archivos).
    """
    import json

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }
    client.set_bucket_policy(bucket, json.dumps(policy))


