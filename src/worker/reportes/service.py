"""Orquestacion: validar -> consultar -> generar -> publicar (User Story 1)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.worker.events.schemas import EstadoReporte, ReporteGenerado, SolicitudDeReporte


class AnuncioInexistente(Exception):
    """Se levanta cuando el `anuncio_id` de la solicitud no existe (User Story 2)."""


def procesar_solicitud(
    solicitud: SolicitudDeReporte,
    *,
    repository,
    excel_builder,
    publisher,
    idempotencia=None,
) -> ReporteGenerado | None:
    """Orquesta el flujo completo para una `SolicitudDeReporte` ya validada.

    No publica `reporte.listo` si la consulta o la generacion fallan (la excepcion
    se propaga sin capturar, dejando la decision de ack/nack al consumer). Si se
    provee `idempotencia`, se verifica primero si la solicitud ya fue completada
    (User Story 3): en ese caso no se reprocesa. Ante exito se marca `completado`;
    ante excepcion se marca `fallido` y se re-propaga (sin duplicar trabajo en el
    reintento posterior).
    """

    if idempotencia is not None and idempotencia.esta_completado(solicitud.solicitud_id):
        return None

    if idempotencia is not None:
        idempotencia.marcar_en_proceso(solicitud.solicitud_id)

    if hasattr(repository, "anuncio_existe") and not repository.anuncio_existe(
        solicitud.anuncio_id
    ):
        raise AnuncioInexistente(
            f"anuncio_id={solicitud.anuncio_id!r} no existe en la tabla anuncio"
        )

    try:
        eventos = list(
            repository.obtener_eventos_anuncio(
                solicitud.anuncio_id, solicitud.fecha_desde, solicitud.fecha_hasta
            )
        )

        excel_builder.construir_reporte(eventos)

        estado = EstadoReporte.GENERADO if eventos else EstadoReporte.VACIO

        reporte = ReporteGenerado(
            solicitud_id=solicitud.solicitud_id,
            # La referencia real al objeto persistido la resuelve 002-minio-storage;
            # aqui se usa un placeholder determinista hasta esa integracion.
            referencia_archivo=f"reportes/{solicitud.anuncio_id}/{solicitud.solicitud_id}.xlsx",
            estado=estado,
            generado_en=datetime.now(timezone.utc),
        )

        publisher.publicar_reporte_listo(reporte)
    except Exception:
        if idempotencia is not None:
            idempotencia.marcar_fallido(solicitud.solicitud_id)
        raise

    if idempotencia is not None:
        idempotencia.marcar_completado(solicitud.solicitud_id)

    return reporte
