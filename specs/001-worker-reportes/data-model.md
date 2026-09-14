# Data Model: Worker de Generación de Reportes

**Feature**: `001-worker-reportes` | **Date**: 2026-09-14

## Entidades

### Anuncio (tabla compartida `anuncio`, propiedad coordinada con `api-general`)

Representa un anuncio del sistema y sus eventos de interacción. **El schema exacto y
autoritativo vive documentado en `api-general`**; lo aquí descrito es la interpretación
de trabajo de este repo, a validar/sincronizar antes de implementar.

| Campo | Tipo | Notas |
|---|---|---|
| `anuncio_id` | UUID / int | Identificador del anuncio. Clave de filtrado principal. |
| `tipo_evento` | enum (`impresion`, `click`) | Determina a qué hoja del Excel pertenece el registro. |
| `timestamp` | datetime (UTC) | Momento del evento. Puede ser `NULL` en registros corruptos (Clarification #3) → se marca "N/D". |
| `usuario_id` | UUID / int, nullable | Usuario que generó la impresión/click, si está disponible. |
| `metadata` | JSON/columnas adicionales | Campos adicionales del anuncio relevantes para el reporte (a confirmar con `api-general`). |

**Reglas de negocio**:
- Un registro con `timestamp` nulo o fuera de un formato válido se incluye igual en el
  Excel, marcando el campo afectado como `"N/D"` (FR-010, Clarification #3).
- El filtrado por rango de fechas se aplica sobre `timestamp` solo para registros que sí
  tienen un `timestamp` válido. Todo registro del mismo `anuncio_id` con `timestamp`
  nulo/no interpretable se incluye siempre, sin importar el rango solicitado (FR-003,
  FR-010, Clarification #6). La query SQL debe reflejar esto como un `OR` explícito
  (`timestamp BETWEEN :desde AND :hasta OR timestamp IS NULL`), no como una exclusión
  implícita del filtro.

### SolicitudDeReporte (payload de evento `reporte.generar`, entrante)

| Campo | Tipo | Requerido | Notas |
|---|---|---|---|
| `solicitud_id` | UUID | Sí | Generado por `api-general`. Clave de idempotencia (FR-008). |
| `anuncio_id` | UUID / int | Sí | Debe existir en `anuncio` (FR-005). |
| `fecha_desde` | date/datetime | Sí | Inicio del rango. |
| `fecha_hasta` | date/datetime | Sí | Fin del rango; debe ser posterior o igual a `fecha_desde` (Edge Case spec). |
| `usuario_solicitante` | UUID / string | Sí | Para trazabilidad; no se revalida permiso de negocio en este worker (Assumption spec). |

**Validación**: modelo `pydantic` estricto (`extra="forbid"` recomendado) para detectar
campos inesperados o tipos incorrectos y rechazar (FR-001, FR-002).

### ReporteGenerado (payload de evento `reporte.listo`, saliente)

| Campo | Tipo | Requerido | Notas |
|---|---|---|---|
| `solicitud_id` | UUID | Sí | Igual al recibido, para correlación en `api-general`. |
| `referencia_archivo` | string | Sí | Puntero lógico al archivo (bucket/key o identificador interno); la resolución final a URL es de la feature `002-minio-storage`. |
| `estado` | enum (`generado`, `vacio`) | Sí | Distingue reporte con datos vs. reporte sin datos en el rango (User Story 1, Scenario 2). |
| `generado_en` | datetime (UTC) | Sí | Timestamp de finalización de la generación. |

### RegistroDeIdempotencia (tabla propia de este repo, NO compartida)

| Campo | Tipo | Notas |
|---|---|---|
| `solicitud_id` | UUID (PK) | Igual al de `SolicitudDeReporte`. |
| `estado` | enum (`en_proceso`, `completado`, `fallido`) | Controla reprocesamiento concurrente/duplicado. |
| `creado_en` | datetime | Momento en que se empezó a procesar. |
| `completado_en` | datetime, nullable | Momento de finalización exitosa. |

**Reglas de negocio**:
- Antes de procesar un evento, se verifica si `solicitud_id` ya está `completado` → se
  hace ack sin reprocesar (evita duplicados, FR-008, SC-003).
- Si está `en_proceso` por otra tarea concurrente, se difiere/reintenta sin duplicar
  trabajo.
- Esta tabla es propiedad exclusiva de este repo (no es la tabla `anuncio` compartida);
  no amplía la excepción de aislamiento de datos del Principio II.

## Relaciones

```text
SolicitudDeReporte (evento entrante)
        │
        │ 1:1 (por solicitud_id)
        ▼
RegistroDeIdempotencia ──── controla ────▶ procesamiento único por solicitud_id
        │
        │ dispara consulta filtrada por anuncio_id + rango
        ▼
Anuncio (N registros: impresiones/clicks) ──── se transforma en ────▶ Excel (2 hojas)
        │
        ▼
ReporteGenerado (evento saliente, referencia lógica al archivo)
```

## Transiciones de estado (RegistroDeIdempotencia)

```text
(no existe) → en_proceso → completado
                  │
                  └──▶ fallido → (reintento) → en_proceso → completado
```
