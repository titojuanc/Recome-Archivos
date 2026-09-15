"""Orquestacion: validar -> consultar -> generar -> publicar (User Story 1)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.worker.events.schemas import EstadoReporte, ReporteGenerado, SolicitudDeReporte

logger = logging.getLogger("worker.reportes.service")


class AnuncioInexistente(Exception):
    """Se levanta cuando el `anuncio_id` de la solicitud no existe (User Story 2)."""


def procesar_solicitud(
    solicitud: SolicitudDeReporte,
    *,
    repository,
    excel_builder,
    publisher,
    idempotencia=None,
    persistencia=None,
) -> ReporteGenerado | None:
    """Orquesta el flujo completo para una `SolicitudDeReporte` ya validada.

    No publica `reporte.listo` si la consulta o la generacion fallan (la excepcion
    se propaga sin capturar, dejando la decision de ack/nack al consumer). Si se
    provee `idempotencia`, se verifica primero si la solicitud ya fue completada
    (User Story 3): en ese caso no se reprocesa. Ante exito se marca `completado`;
    ante excepcion se marca `fallido` y se re-propaga (sin duplicar trabajo en el
    reintento posterior).
    """

    sid = solicitud.solicitud_id

    if idempotencia is not None and idempotencia.esta_completado(sid):
        logger.info("solicitud_id=%s ya completada, omitiendo reprocesamiento", sid)
        return None

    if idempotencia is not None:
        idempotencia.marcar_en_proceso(sid)
        logger.info("solicitud_id=%s marcada en_proceso", sid)

    if hasattr(repository, "anuncio_existe") and not repository.anuncio_existe(
        solicitud.anuncio_id
    ):
        logger.warning(
            "solicitud_id=%s anuncio_id=%s no existe", sid, solicitud.anuncio_id
        )
        raise AnuncioInexistente(
            f"anuncio_id={solicitud.anuncio_id!r} no existe en la tabla anuncio"
        )

    try:
        logger.info(
            "solicitud_id=%s consultando eventos anuncio_id=%s rango=[%s, %s]",
            sid,
            solicitud.anuncio_id,
            solicitud.fecha_desde,
            solicitud.fecha_hasta,
        )
        eventos = list(
            repository.obtener_eventos_anuncio(
                solicitud.anuncio_id, solicitud.fecha_desde, solicitud.fecha_hasta
            )
        )

        archivo_excel = excel_builder.construir_reporte(eventos)

        estado = EstadoReporte.GENERADO if eventos else EstadoReporte.VACIO
        logger.info("solicitud_id=%s reporte generado estado=%s", sid, estado.value)

        if persistencia is not None:
            referencia = persistencia.subir_reporte(
                solicitud.anuncio_id, str(sid), archivo_excel
            )
            referencia_archivo = f"{referencia.bucket}/{referencia.key}"
            logger.info(
                "solicitud_id=%s reporte persistido en %s", sid, referencia_archivo
            )
        else:
            # Placeholder hasta que 002-minio-storage este completamente integrado.
            referencia_archivo = f"reportes/{solicitud.anuncio_id}/{sid}.xlsx"

        reporte = ReporteGenerado(
            solicitud_id=sid,
            referencia_archivo=referencia_archivo,
            estado=estado,
            generado_en=datetime.now(timezone.utc),
        )

        publisher.publicar_reporte_listo(reporte)
        logger.info("solicitud_id=%s reporte.listo publicado", sid)
    except Exception:
        logger.exception("solicitud_id=%s fallo durante el procesamiento", sid)
        if idempotencia is not None:
            idempotencia.marcar_fallido(sid)
        raise

    if idempotencia is not None:
        idempotencia.marcar_completado(sid)
        logger.info("solicitud_id=%s marcada completado", sid)

    return reporte
