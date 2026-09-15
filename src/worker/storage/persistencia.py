"""Persistencia de reportes generados en MinIO (subida con integridad bloqueante)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import BinaryIO

from minio import Minio

from src.worker.storage.key_builder import construir_key


class FalloDePersistencia(Exception):
    """Se lanza cuando la subida a MinIO no puede garantizarse íntegra."""


@dataclass(frozen=True)
class ReferenciaDeArchivo:
    bucket: str
    key: str
    etag: str


def calcular_checksum(archivo: BinaryIO) -> str:
    """Calcula un hash MD5 reproducible sobre el contenido completo del stream."""
    posicion_original = archivo.tell()
    archivo.seek(0)
    hasher = hashlib.md5()
    for bloque in iter(lambda: archivo.read(8192), b""):
        hasher.update(bloque)
    archivo.seek(posicion_original)
    return hasher.hexdigest()


def subir_reporte(
    anuncio_id: str,
    solicitud_id: str,
    archivo: BinaryIO,
    *,
    client: Minio,
    bucket: str,
) -> ReferenciaDeArchivo:
    """Sube el archivo a MinIO en una key determinística y verifica su integridad.

    No realiza ningún chequeo de existencia previa (stat_object): reintentar con el
    mismo anuncio_id/solicitud_id simplemente sobrescribe el objeto (US2, FR-006).
    Si el ETag devuelto no coincide con el checksum local, se lanza
    FalloDePersistencia y la solicitud no debe considerarse completada (FR-004).
    """
    key = construir_key(anuncio_id, solicitud_id)
    checksum_local = calcular_checksum(archivo)

    archivo.seek(0)
    archivo.seek(0, 2)
    tamano = archivo.tell()
    archivo.seek(0)

    resultado = client.put_object(bucket, key, archivo, length=tamano)

    etag = (resultado.etag or "").strip('"')
    if etag != checksum_local:
        raise FalloDePersistencia(
            f"ETag devuelto por MinIO ({etag}) no coincide con el checksum local "
            f"({checksum_local}) para key={key}"
        )

    return ReferenciaDeArchivo(bucket=bucket, key=key, etag=etag)
