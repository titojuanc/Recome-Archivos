"""Orquestacion: validar -> consultar -> generar -> publicar (User Story 1).

El reporte cubre TODOS los anuncios del vendedor (no uno puntual): la
solicitud trae `anuncio_ids` (lista), y se consolida un unico Excel con la
actividad de todos ellos, separada prolijamente por anuncio.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.worker.events.schemas import EstadoReporte, ReporteGenerado, SolicitudDeReporte

logger = logging.getLogger("worker.reportes.service")


class AnuncioInexistente(Exception):
    """Se levanta cuando NINGUNO de los `anuncio_ids` de la solicitud existe
    (User Story 2). Si solo alguno no existe, se omite con un warning y se
    sigue con el resto (no se aborta todo el reporte por un anuncio borrado)."""


def procesar_solicitud(
    solicitud: SolicitudDeReporte,
    *,
    repository,
    excel_builder,
    publisher,
    idempotencia=None,
    persistencia=None,
    autorizacion_repository=None,
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

    anuncio_ids_validos = list(solicitud.anuncio_ids)
    if hasattr(repository, "anuncio_existe"):
        anuncio_ids_validos = []
        for anuncio_id in solicitud.anuncio_ids:
            if repository.anuncio_existe(anuncio_id):
                anuncio_ids_validos.append(anuncio_id)
            else:
                logger.warning(
                    "solicitud_id=%s anuncio_id=%s no existe, se omite del consolidado",
                    sid, anuncio_id,
                )
        if not anuncio_ids_validos:
            raise AnuncioInexistente(
                f"ninguno de los anuncio_ids={solicitud.anuncio_ids!r} existe en la tabla anuncio"
            )

    try:
        logger.info(
            "solicitud_id=%s consultando eventos anuncio_ids=%s rango=[%s, %s]",
            sid,
            anuncio_ids_validos,
            solicitud.fecha_desde,
            solicitud.fecha_hasta,
        )
        eventos = list(
            repository.obtener_eventos_multiples_anuncios(
                anuncio_ids_validos, solicitud.fecha_desde, solicitud.fecha_hasta
            )
        )

        archivo_excel = excel_builder.construir_reporte(eventos)

        estado = EstadoReporte.GENERADO if eventos else EstadoReporte.VACIO
        logger.info("solicitud_id=%s reporte generado estado=%s", sid, estado.value)

        url_descarga = None
        if persistencia is not None:
            referencia = persistencia.subir_reporte(str(sid), archivo_excel)
            referencia_archivo = f"{referencia.bucket}/{referencia.key}"
            url_descarga = getattr(referencia, "url_descarga", None)
            logger.info(
                "solicitud_id=%s reporte persistido en %s", sid, referencia_archivo
            )
            if autorizacion_repository is not None:
                autorizacion_repository.registrar_autorizacion(
                    solicitud_id=sid,
                    anuncio_id=",".join(anuncio_ids_validos),
                    usuario_solicitante=solicitud.usuario_solicitante,
                    bucket=referencia.bucket,
                    key=referencia.key,
                )
                logger.info("solicitud_id=%s autorizacion registrada", sid)
        else:
            # Placeholder hasta que 002-minio-storage este completamente integrado.
            referencia_archivo = f"reportes/{sid}.xlsx"

        reporte = ReporteGenerado(
            solicitud_id=sid,
            referencia_archivo=referencia_archivo,
            estado=estado,
            generado_en=datetime.now(timezone.utc),
            url_descarga=url_descarga,
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
