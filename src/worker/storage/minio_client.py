"""Wrapper del SDK oficial de MinIO: conexion y verificacion/creacion de bucket."""

from __future__ import annotations

from minio import Minio


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
