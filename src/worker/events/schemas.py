"""Modelos pydantic que reflejan los contratos documentados en api-general.

Fuente de verdad externa (Principio III de la constitution):
- specs/001-worker-reportes/contracts/reporte.generar.schema.json
- specs/001-worker-reportes/contracts/reporte.listo.schema.json
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SolicitudDeReporte(BaseModel):
    """Payload entrante del evento `reporte.generar`.

    `anuncio_ids` reemplaza al antiguo `anuncio_id` singular: el reporte ahora
    cubre TODA la actividad del vendedor (todos sus anuncios) en el rango de
    fechas solicitado, no un anuncio puntual.
    """

    model_config = ConfigDict(extra="forbid")

    solicitud_id: UUID
    anuncio_ids: list[str] = Field(min_length=1)
    fecha_desde: datetime
    fecha_hasta: datetime
    usuario_solicitante: str

    @model_validator(mode="after")
    def _validar_rango_de_fechas(self) -> "SolicitudDeReporte":
        if self.fecha_desde > self.fecha_hasta:
            raise ValueError("fecha_desde debe ser anterior o igual a fecha_hasta")
        return self


class EstadoReporte(str, Enum):
    GENERADO = "generado"
    VACIO = "vacio"


class ReporteGenerado(BaseModel):
    """Payload saliente del evento `reporte.listo`."""

    model_config = ConfigDict(extra="forbid")

    solicitud_id: UUID
    referencia_archivo: str
    estado: EstadoReporte
    generado_en: datetime
    url_descarga: str | None = None
    """URL firmada (presigned) de MinIO para descargar el archivo directamente,
    usada por api-general en e2e-local para adjuntarlo al mail de notificación."""
