"""Construccion deterministica de keys de objetos en MinIO para reportes."""

from __future__ import annotations


def construir_key(solicitud_id: str) -> str:
    """Devuelve la key determinística `reportes/{solicitud_id}.xlsx`.

    Antes incluía el `anuncio_id` (reporte de un anuncio puntual); ahora el
    reporte es consolidado (todos los anuncios de un vendedor), así que la
    única clave natural es `solicitud_id`.
    """
    return f"reportes/{solicitud_id}.xlsx"
