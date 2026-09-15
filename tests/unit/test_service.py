"""Unit tests: service.procesar_solicitud() orquesta validar->consultar->generar->publicar.

Deben FALLAR hasta que exista src/worker/reportes/service.py (TDD estricto).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.worker.events.schemas import EstadoReporte, SolicitudDeReporte


@pytest.fixture()
def solicitud_valida() -> SolicitudDeReporte:
    return SolicitudDeReporte(
        solicitud_id=uuid4(),
        anuncio_id="anuncio-123",
        fecha_desde=datetime(2020, 1, 1, tzinfo=timezone.utc),
        fecha_hasta=datetime(2030, 1, 1, tzinfo=timezone.utc),
        usuario_solicitante="user-1",
    )


def test_procesar_solicitud_orquesta_flujo_completo_y_publica(solicitud_valida):
    from src.worker.reportes.service import procesar_solicitud

    repo = MagicMock(obtener_eventos_anuncio=MagicMock(return_value=iter([MagicMock()])))
    excel_builder = MagicMock(construir_reporte=MagicMock(return_value=b"excel-bytes"))
    publisher = MagicMock()

    procesar_solicitud(
        solicitud_valida,
        repository=repo,
        excel_builder=excel_builder,
        publisher=publisher,
    )

    repo.obtener_eventos_anuncio.assert_called_once()
    excel_builder.construir_reporte.assert_called_once()
    publisher.publicar_reporte_listo.assert_called_once()

    _, kwargs = publisher.publicar_reporte_listo.call_args
    reporte = kwargs.get("reporte") or publisher.publicar_reporte_listo.call_args.args[0]
    assert reporte.estado == EstadoReporte.GENERADO


def test_procesar_solicitud_no_publica_si_consulta_falla(solicitud_valida):
    from src.worker.reportes.service import procesar_solicitud

    repo = MagicMock(obtener_eventos_anuncio=MagicMock(side_effect=RuntimeError("db caida")))
    excel_builder = MagicMock()
    publisher = MagicMock()

    with pytest.raises(RuntimeError):
        procesar_solicitud(
            solicitud_valida,
            repository=repo,
            excel_builder=excel_builder,
            publisher=publisher,
        )

    excel_builder.construir_reporte.assert_not_called()
    publisher.publicar_reporte_listo.assert_not_called()


def test_procesar_solicitud_marca_estado_vacio_sin_eventos(solicitud_valida):
    from src.worker.reportes.service import procesar_solicitud

    repo = MagicMock(obtener_eventos_anuncio=MagicMock(return_value=iter([])))
    excel_builder = MagicMock(construir_reporte=MagicMock(return_value=b"excel-bytes"))
    publisher = MagicMock()

    procesar_solicitud(
        solicitud_valida,
        repository=repo,
        excel_builder=excel_builder,
        publisher=publisher,
    )

    args, kwargs = publisher.publicar_reporte_listo.call_args
    reporte = kwargs.get("reporte") or args[0]
    assert reporte.estado == EstadoReporte.VACIO


# --- User Story 2: rechazar eventos invalidos o mal formados ---


def test_solicitud_de_reporte_rechaza_payload_sin_anuncio_id():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SolicitudDeReporte(
            solicitud_id=uuid4(),
            fecha_desde=datetime(2020, 1, 1, tzinfo=timezone.utc),
            fecha_hasta=datetime(2030, 1, 1, tzinfo=timezone.utc),
            usuario_solicitante="user-1",
        )


def test_solicitud_de_reporte_rechaza_rango_de_fechas_invertido():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SolicitudDeReporte(
            solicitud_id=uuid4(),
            anuncio_id="anuncio-123",
            fecha_desde=datetime(2030, 1, 1, tzinfo=timezone.utc),
            fecha_hasta=datetime(2020, 1, 1, tzinfo=timezone.utc),
            usuario_solicitante="user-1",
        )


def test_procesar_solicitud_rechaza_anuncio_id_inexistente(solicitud_valida):
    from src.worker.reportes.service import AnuncioInexistente, procesar_solicitud

    repo = MagicMock(anuncio_existe=MagicMock(return_value=False))
    excel_builder = MagicMock()
    publisher = MagicMock()

    with pytest.raises(AnuncioInexistente):
        procesar_solicitud(
            solicitud_valida,
            repository=repo,
            excel_builder=excel_builder,
            publisher=publisher,
        )

    excel_builder.construir_reporte.assert_not_called()
    publisher.publicar_reporte_listo.assert_not_called()


def test_procesar_solicitud_no_confunde_anuncio_inexistente_con_anuncio_vacio(solicitud_valida):
    """anuncio_id existente sin datos en el rango -> estado 'vacio' (US1 Scenario 2),
    NO debe levantar AnuncioInexistente."""

    from src.worker.reportes.service import procesar_solicitud

    repo = MagicMock(
        anuncio_existe=MagicMock(return_value=True),
        obtener_eventos_anuncio=MagicMock(return_value=iter([])),
    )
    excel_builder = MagicMock(construir_reporte=MagicMock(return_value=b"excel-bytes"))
    publisher = MagicMock()

    procesar_solicitud(
        solicitud_valida,
        repository=repo,
        excel_builder=excel_builder,
        publisher=publisher,
    )

    args, kwargs = publisher.publicar_reporte_listo.call_args
    reporte = kwargs.get("reporte") or args[0]
    assert reporte.estado == EstadoReporte.VACIO
