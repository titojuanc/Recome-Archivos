"""Consumo de `reporte.generar`: ack solo tras exito completo, nack + dead-letter ante
fallos de validacion (User Story 1 + User Story 2)."""

from __future__ import annotations

import json
import logging

import pika
from pydantic import ValidationError

from src.worker.events.schemas import SolicitudDeReporte
from src.worker.reportes.service import AnuncioInexistente, procesar_solicitud

logger = logging.getLogger("worker.consumer")


class Consumer:
    def __init__(
        self,
        *,
        channel,
        repository,
        excel_builder,
        publisher,
        idempotencia=None,
        persistencia=None,
        autorizacion_repository=None,
    ):
        self._channel = channel
        self._repository = repository
        self._excel_builder = excel_builder
        self._publisher = publisher
        self._idempotencia = idempotencia
        self._persistencia = persistencia
        self._autorizacion_repository = autorizacion_repository

    def procesar_mensaje(self, ch, method, properties, body: bytes) -> None:
        try:
            payload = json.loads(body)
            solicitud = SolicitudDeReporte(**payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Mensaje invalido, rechazando (nack + dead-letter): %s", exc)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        try:
            procesar_solicitud(
                solicitud,
                repository=self._repository,
                excel_builder=self._excel_builder,
                publisher=self._publisher,
                idempotencia=self._idempotencia,
                persistencia=self._persistencia,
                autorizacion_repository=self._autorizacion_repository,
            )
        except AnuncioInexistente as exc:
            logger.warning("anuncio_id inexistente, rechazando: %s", exc)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        except Exception:
            logger.exception(
                "Fallo transitorio procesando solicitud_id=%s; no se hace ack",
                solicitud.solicitud_id,
            )
            # No-ack: el mensaje vuelve a la cola para reintento (FR-005/FR-007 de 002,
            # y User Story 3 de 001-worker-reportes).
            return

        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("solicitud_id=%s procesada y ack-eada correctamente", solicitud.solicitud_id)
