"""Modelos pydantic que reflejan los contratos documentados en api-general.

Fuente de verdad externa (Principio III de la constitution):
- specs/001-worker-reportes/contracts/reporte.generar.schema.json
- specs/001-worker-reportes/contracts/reporte.listo.schema.json
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class SolicitudDeReporte(BaseModel):
    """Payload entrante del evento `reporte.generar`."""

    model_config = ConfigDict(extra="forbid")

    solicitud_id: UUID
    anuncio_id: str
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
