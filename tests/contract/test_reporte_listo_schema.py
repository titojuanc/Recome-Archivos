"""Contract test: ReporteGenerado valida contra reporte.listo.schema.json.

Este test debe FALLAR hasta que exista src/worker/events/schemas.py::ReporteGenerado
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
    / "reporte.listo.schema.json"
)


@pytest.fixture()
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture()
def payload_valido() -> dict:
    return {
        "solicitud_id": "6f9619ff-8b86-d011-b42d-00cf4fc964ff",
        "referencia_archivo": "reportes/anuncio-123/6f9619ff-8b86-d011-b42d-00cf4fc964ff.xlsx",
        "estado": "generado",
        "generado_en": "2026-09-15T12:00:00Z",
    }


def test_payload_valido_cumple_el_schema_json(schema, payload_valido):
    jsonschema.validate(instance=payload_valido, schema=schema)


def test_reporte_generado_modelo_valida_payload_correcto(payload_valido):
    from src.worker.events.schemas import ReporteGenerado

    reporte = ReporteGenerado(**payload_valido)

    assert str(reporte.solicitud_id) == payload_valido["solicitud_id"]
    assert reporte.estado == "generado"


def test_reporte_generado_rechaza_estado_invalido(payload_valido):
    from pydantic import ValidationError

    from src.worker.events.schemas import ReporteGenerado

    payload_valido["estado"] = "no_es_un_estado_valido"

    with pytest.raises(ValidationError):
        ReporteGenerado(**payload_valido)


def test_reporte_generado_serializa_a_json_conforme_al_schema(schema, payload_valido):
    from src.worker.events.schemas import ReporteGenerado

    reporte = ReporteGenerado(**payload_valido)
    serializado = json.loads(reporte.model_dump_json())

    jsonschema.validate(instance=serializado, schema=schema)
