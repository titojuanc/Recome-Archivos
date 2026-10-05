"""Unit tests: excel_builder.construir_reporte().

El reporte ahora tiene DOS hojas:
- "Detalle": un registro por fila (anuncio_id, timestamp, usuario_id, tipo_actividad).
- "Resumen": totales por anuncio + tabla de actividad por día con gráfico.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import openpyxl
import pytest


class EventoFake:
    """Stub minimo de un registro de `anuncio` para no depender de SQLAlchemy aca."""

    def __init__(self, anuncio_id, tipo_evento, timestamp, usuario_id):
        self.anuncio_id = anuncio_id
        self.tipo_evento = tipo_evento
        self.timestamp = timestamp
        self.usuario_id = usuario_id


@pytest.fixture()
def eventos_mixtos():
    ahora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        EventoFake("anuncio-1", "impresion", ahora, "user-1"),
        EventoFake("anuncio-1", "click", ahora, "user-1"),
        EventoFake("anuncio-1", "impresion", None, None),  # corrupto -> "N/D"
    ]


def _leer_workbook(stream: io.BytesIO):
    stream.seek(0)
    return openpyxl.load_workbook(stream)


def _sin_nones_finales(fila):
    """openpyxl rellena con None hasta el ancho máximo de la hoja al iterar."""
    fila = list(fila)
    while fila and fila[-1] is None:
        fila.pop()
    return tuple(fila)


def test_genera_workbook_con_hojas_detalle_y_resumen(eventos_mixtos):
    from src.worker.reportes.excel_builder import construir_reporte

    buffer = construir_reporte(eventos_mixtos)
    wb = _leer_workbook(buffer)

    assert wb.sheetnames == ["Detalle", "Resumen"]


def test_hoja_detalle_tiene_una_fila_por_evento_con_tipo_actividad(eventos_mixtos):
    from src.worker.reportes.excel_builder import construir_reporte

    buffer = construir_reporte(eventos_mixtos)
    wb = _leer_workbook(buffer)

    filas = list(wb["Detalle"].iter_rows(values_only=True))
    assert filas[0] == ("anuncio_id", "timestamp", "usuario_id", "tipo_actividad")
    # header + 3 eventos, sin filas separadoras (a diferencia del Resumen)
    assert len(filas) == 4
    assert filas[1] == ("anuncio-1", ahora_iso(eventos_mixtos[0].timestamp), "user-1", "impresión")
    assert filas[2][3] == "click"


def ahora_iso(valor):
    return valor.isoformat()


def test_marca_campos_corruptos_como_nd_en_detalle(eventos_mixtos):
    from src.worker.reportes.excel_builder import construir_reporte

    buffer = construir_reporte(eventos_mixtos)
    wb = _leer_workbook(buffer)

    filas = list(wb["Detalle"].iter_rows(values_only=True))
    fila_corrupta = filas[3]
    assert fila_corrupta[1] == "N/D"
    assert fila_corrupta[2] == "N/D"
    assert fila_corrupta[3] == "impresión"


def test_resumen_totaliza_por_anuncio():
    from src.worker.reportes.excel_builder import construir_reporte

    ahora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    eventos = [
        EventoFake("anuncio-1", "impresion", ahora, "user-1"),
        EventoFake("anuncio-1", "impresion", ahora, "user-1"),
        EventoFake("anuncio-1", "click", ahora, "user-1"),
        EventoFake("anuncio-2", "cerrado", ahora, "user-2"),
    ]
    buffer = construir_reporte(eventos)
    wb = _leer_workbook(buffer)

    filas = list(wb["Resumen"].iter_rows(values_only=True))
    assert _sin_nones_finales(filas[0]) == ("Totales por anuncio",)
    assert filas[1] == ("anuncio_id", "impresiones", "clicks", "cierres")
    assert filas[2] == ("anuncio-1", 2, 1, 0)
    assert filas[3] == ("anuncio-2", 0, 0, 1)


def test_resumen_agrega_tabla_de_actividad_por_dia():
    from src.worker.reportes.excel_builder import construir_reporte

    dia1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    dia2 = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    eventos = [
        EventoFake("anuncio-1", "impresion", dia1, "user-1"),
        EventoFake("anuncio-1", "click", dia1, "user-1"),
        EventoFake("anuncio-2", "impresion", dia2, "user-2"),
    ]
    buffer = construir_reporte(eventos)
    wb = _leer_workbook(buffer)

    filas = list(wb["Resumen"].iter_rows(values_only=True))
    # Despues de la tabla de totales (2 anuncios = filas 0..3) viene una fila
    # en blanco, el titulo, el header y 2 filas de datos (una por dia).
    idx_titulo = next(
        i for i, fila in enumerate(filas)
        if _sin_nones_finales(fila) == ("Actividad por día (todos los anuncios)",)
    )
    assert filas[idx_titulo + 1] == ("fecha", "impresiones", "clicks", "cierres")
    assert filas[idx_titulo + 2] == ("2026-01-01", 1, 1, 0)
    assert filas[idx_titulo + 3] == ("2026-01-02", 1, 0, 0)


def test_resumen_incluye_grafico_de_actividad():
    from src.worker.reportes.excel_builder import construir_reporte

    ahora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    eventos = [EventoFake("anuncio-1", "impresion", ahora, "user-1")]
    buffer = construir_reporte(eventos)
    wb = _leer_workbook(buffer)

    charts = wb["Resumen"]._charts
    assert len(charts) == 1
    assert charts[0].title is not None


def test_grafico_tiene_marcadores_visibles_incluso_con_un_solo_dia():
    """Sin marcador, una serie con un único punto no dibuja nada (ni línea
    ni punto), porque una línea necesita al menos 2 puntos para trazarse."""
    from src.worker.reportes.excel_builder import construir_reporte

    ahora = datetime(2026, 1, 1, tzinfo=timezone.utc)
    eventos = [EventoFake("anuncio-1", "impresion", ahora, "user-1")]
    buffer = construir_reporte(eventos)
    wb = _leer_workbook(buffer)

    chart = wb["Resumen"]._charts[0]
    assert len(chart.series) == 3
    for serie in chart.series:
        assert serie.marker is not None
        assert serie.marker.symbol not in (None, "none")


def test_genera_hojas_con_solo_encabezados_cuando_no_hay_datos():
    from src.worker.reportes.excel_builder import construir_reporte

    buffer = construir_reporte([])
    wb = _leer_workbook(buffer)

    filas_detalle = list(wb["Detalle"].iter_rows(values_only=True))
    assert len(filas_detalle) == 1  # solo encabezado

    filas_resumen = list(wb["Resumen"].iter_rows(values_only=True))
    assert _sin_nones_finales(filas_resumen[0]) == ("Totales por anuncio",)
    assert filas_resumen[1] == ("anuncio_id", "impresiones", "clicks", "cierres")
    # Sin anuncios -> sin filas de datos en la tabla de totales (le sigue
    # directo la fila en blanco + titulo + header de la tabla de actividad).
    assert _sin_nones_finales(filas_resumen[3]) == ("Actividad por día (todos los anuncios)",)
    assert filas_resumen[4] == ("fecha", "impresiones", "clicks", "cierres")
    assert len(filas_resumen) == 5
    # Sin dias -> sin grafico.
    assert len(wb["Resumen"]._charts) == 0
