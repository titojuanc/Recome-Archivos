"""Generacion del Excel de reporte consolidado (dos hojas: Detalle/Resumen).

El reporte cubre TODOS los anuncios de un vendedor a la vez (no uno puntual):

- Hoja "Detalle": un registro por fila con anuncio_id, timestamp, usuario_id,
  tipo_actividad (impresión/click/cierre). Es el detalle "crudo" de cada
  evento, en el orden en que llega (agrupado por anuncio_id, ver
  `repository.obtener_eventos_multiples_anuncios`).
- Hoja "Resumen": totales de impresiones/clicks/cierres por anuncio, y una
  tabla + gráfico de actividad por día (suma de los 3 tipos, agregada entre
  todos los anuncios) para que el vendedor identifique picos/caídas de
  actividad en el tiempo de un vistazo.

NOTA: a diferencia de la version anterior, ya NO se usa el modo `write_only`
de openpyxl: para poder calcular los totales del Resumen y agregar un gráfico
nativo de Excel hace falta un workbook "normal" (write_only no soporta
gráficos ni mantiene las hojas accesibles para leer/agregar luego). El reporte
sigue siendo razonable en memoria porque se agrega sobre la marcha, en un
solo pasada por `eventos` (no se guarda la lista completa de eventos, solo
los contadores agregados y las filas ya escritas en la hoja Detalle).
"""

from __future__ import annotations

import io
from collections import OrderedDict
from typing import Iterable

import openpyxl
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.marker import Marker

_NA = "N/D"

_ENCABEZADOS_DETALLE = ("anuncio_id", "timestamp", "usuario_id", "tipo_actividad")

_TIPO_A_ETIQUETA = {
    "impresion": "impresión",
    "click": "click",
    "cerrado": "cierre",
}

# Orden fijo de columnas para las tablas de totales del Resumen.
_TIPOS_ORDENADOS = ("impresion", "click", "cerrado")
_ETIQUETAS_COLUMNAS = ("impresiones", "clicks", "cierres")


def _valor_o_nd(valor):
    if valor is None:
        return _NA
    if hasattr(valor, "isoformat"):
        # Excel no soporta timezone-aware datetimes; se serializa como ISO-8601 string.
        return valor.isoformat()
    return valor


def _dia_o_nd(timestamp) -> str:
    if timestamp is None:
        return _NA
    return timestamp.date().isoformat()


def construir_reporte(eventos: Iterable) -> io.BytesIO:
    """Construye el workbook de dos hojas (Detalle + Resumen) a partir de un
    iterable de eventos.

    Cada evento debe exponer `anuncio_id`, `tipo_evento`, `timestamp`, `usuario_id`.
    """

    wb = openpyxl.Workbook()
    ws_detalle = wb.active
    ws_detalle.title = "Detalle"
    ws_detalle.append(_ENCABEZADOS_DETALLE)

    # anuncio_id -> {tipo_evento: cantidad}
    totales_por_anuncio: "OrderedDict[object, dict[str, int]]" = OrderedDict()
    # dia (ISO) o "N/D" -> {tipo_evento: cantidad}
    actividad_por_dia: "OrderedDict[str, dict[str, int]]" = OrderedDict()

    for evento in eventos:
        etiqueta = _TIPO_A_ETIQUETA.get(evento.tipo_evento, evento.tipo_evento)
        ws_detalle.append((
            evento.anuncio_id,
            _valor_o_nd(evento.timestamp),
            _valor_o_nd(evento.usuario_id),
            etiqueta,
        ))

        contador_anuncio = totales_por_anuncio.setdefault(evento.anuncio_id, {})
        contador_anuncio[evento.tipo_evento] = contador_anuncio.get(evento.tipo_evento, 0) + 1

        dia = _dia_o_nd(evento.timestamp)
        contador_dia = actividad_por_dia.setdefault(dia, {})
        contador_dia[evento.tipo_evento] = contador_dia.get(evento.tipo_evento, 0) + 1

    _escribir_resumen(wb, totales_por_anuncio, actividad_por_dia)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def _escribir_resumen(wb, totales_por_anuncio, actividad_por_dia) -> None:
    ws = wb.create_sheet("Resumen")

    # --- Tabla 1: totales por anuncio --------------------------------------
    ws.append(("Totales por anuncio",))
    fila_header_totales = ws.max_row + 1
    ws.append(("anuncio_id", *_ETIQUETAS_COLUMNAS))
    for anuncio_id in sorted(totales_por_anuncio, key=str):
        contador = totales_por_anuncio[anuncio_id]
        ws.append((anuncio_id, *(contador.get(tipo, 0) for tipo in _TIPOS_ORDENADOS)))
    fila_fin_totales = ws.max_row

    # --- Tabla 2: actividad por día (para el gráfico) -----------------------
    ws.append(())  # fila en blanco separadora
    ws.append(("Actividad por día (todos los anuncios)",))
    fila_titulo_dia = ws.max_row
    fila_header_dia = fila_titulo_dia + 1
    ws.append(("fecha", *_ETIQUETAS_COLUMNAS))

    dias_ordenados = sorted(actividad_por_dia, key=lambda d: (d == _NA, d))
    for dia in dias_ordenados:
        contador = actividad_por_dia[dia]
        ws.append((dia, *(contador.get(tipo, 0) for tipo in _TIPOS_ORDENADOS)))
    fila_fin_dia = ws.max_row

    if dias_ordenados:
        _agregar_grafico_actividad(ws, fila_header_dia, fila_fin_dia)


def _agregar_grafico_actividad(ws, fila_header_dia: int, fila_fin_dia: int) -> None:
    """Agrega un gráfico de líneas (actividad en el tiempo) anclado a la
    derecha de la tabla "Actividad por día", para ayudar a identificar
    visualmente picos/caídas de actividad."""

    chart = LineChart()
    chart.title = "Actividad en el tiempo"
    chart.y_axis.title = "Cantidad de eventos"
    chart.x_axis.title = "Fecha"
    chart.style = 10

    # Columnas impresiones/clicks/cierres (B..D), con el header como nombre de serie.
    datos = Reference(ws, min_col=2, max_col=4, min_row=fila_header_dia, max_row=fila_fin_dia)
    categorias = Reference(ws, min_col=1, min_row=fila_header_dia + 1, max_row=fila_fin_dia)
    chart.add_data(datos, titles_from_data=True)
    chart.set_categories(categorias)

    # Por defecto openpyxl no dibuja marcadores: con un solo día de datos no
    # hay segmento de línea que trazar, y sin marcador el punto no se ve en
    # absoluto (parece un gráfico "vacío"). Se fuerza un marcador circular en
    # cada serie para que cualquier cantidad de días (incluido uno solo) sea
    # visible.
    for serie in chart.series:
        serie.marker = Marker(symbol="circle", size=7)
        serie.smooth = False

    ws.add_chart(chart, f"G{fila_header_dia}")
