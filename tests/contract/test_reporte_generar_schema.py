"""Contract test: SolicitudDeReporte valida contra reporte.generar.schema.json.

Este test debe FALLAR hasta que exista src/worker/events/schemas.py::SolicitudDeReporte
(TDD estricto, Principio VII de la constitution).
"""

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "001-worker-reportes"
    / "contracts"
    / "reporte.generar.schema.json"
)


@pytest.fixture()
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture()
def payload_valido() -> dict:
    return {
        "solicitud_id": "6f9619ff-8b86-d011-b42d-00cf4fc964ff",
        "anuncio_id": "anuncio-123",
        "fecha_desde": "2020-01-01T00:00:00Z",
        "fecha_hasta": "2030-01-01T00:00:00Z",
        "usuario_solicitante": "user-1",
    }


def test_payload_valido_cumple_el_schema_json(schema, payload_valido):
    jsonschema.validate(instance=payload_valido, schema=schema)


def test_solicitud_de_reporte_modelo_valida_payload_correcto(payload_valido):
    from src.worker.events.schemas import SolicitudDeReporte

    solicitud = SolicitudDeReporte(**payload_valido)

    assert str(solicitud.solicitud_id) == payload_valido["solicitud_id"]
    assert solicitud.anuncio_id == payload_valido["anuncio_id"]
    assert solicitud.usuario_solicitante == payload_valido["usuario_solicitante"]


def test_solicitud_de_reporte_rechaza_campos_extra(payload_valido):
    from pydantic import ValidationError

    from src.worker.events.schemas import SolicitudDeReporte

    payload_valido["campo_inesperado"] = "no deberia estar aca"

    with pytest.raises(ValidationError):
        SolicitudDeReporte(**payload_valido)


def test_solicitud_de_reporte_rechaza_falta_de_anuncio_id(payload_valido):
    from pydantic import ValidationError

    from src.worker.events.schemas import SolicitudDeReporte

    del payload_valido["anuncio_id"]

    with pytest.raises(ValidationError):
        SolicitudDeReporte(**payload_valido)
