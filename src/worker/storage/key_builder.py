"""Construccion deterministica de keys de objetos en MinIO para reportes."""

from __future__ import annotations


def construir_key(anuncio_id: str, solicitud_id: str) -> str:
    """Devuelve la key determinística `reportes/{anuncio_id}/{solicitud_id}.xlsx`."""
    return f"reportes/{anuncio_id}/{solicitud_id}.xlsx"
