# Data Model: Persistencia de Reportes en MinIO

**Feature**: `002-minio-storage` | **Date**: 2026-09-15

## Entidades

### ObjetoDeReporte (objeto persistido en MinIO)

| Campo | Tipo | Notas |
|---|---|---|
| `bucket` | string | Bucket exclusivo de este repo (configurable por entorno). |
| `key` | string | `reportes/{anuncio_id}/{solicitud_id}.xlsx` — determinística (research.md #2). |
| `etag` | string | Devuelto por MinIO tras la subida; usado para verificación de integridad (FR-004). |
| `tamanio_bytes` | int | Tamaño del objeto subido. |
| `generado_en` | datetime (UTC) | Guardado como metadata de usuario del objeto (`x-amz-meta-generado-en`); insumo de la política de retención. |
| `content_type` | string | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

**Reglas de negocio**:
- La `key` se deriva exclusivamente del `solicitud_id` (y `anuncio_id` como prefijo de
  organización), nunca de un contador o timestamp, para garantizar determinismo (FR-002).
- Un objeto no se considera "persistido exitosamente" hasta que el `etag` devuelto por
  MinIO coincide con el checksum local calculado antes de subir (FR-004).

### ReferenciaDeArchivo (payload incluido en el evento `reporte.listo`, ya definido en `001-worker-reportes/contracts/reporte.listo.schema.json` como `referencia_archivo`)

Esta feature **no redefine** el schema de `reporte.listo`; produce el valor concreto que
llena el campo `referencia_archivo` de ese contrato ya existente.

| Campo lógico | Origen | Notas |
|---|---|---|
| `referencia_archivo` | `f"{bucket}/{key}"` o un identificador interno equivalente | Debe ser suficiente para que la feature `003-webserver-archivos` resuelva el objeto sin contexto adicional. |

### PoliticaDeRetencion (configuración, no una entidad persistida por solicitud)

| Campo | Tipo | Notas |
|---|---|---|
| `dias_retencion` | int | Configurable por entorno (Assumption del spec). |
| `prefijo_alcance` | string | `reportes/` — alcance del job de limpieza, para no afectar otros posibles usos futuros del bucket. |

**Reglas de negocio**:
- Un objeto se elimina cuando `now() - generado_en > dias_retencion`.
- El job de limpieza (`retencion.py`) opera por prefijo y metadata, sin necesitar una
  tabla SQL auxiliar (research.md #6).

## Relaciones

```text
ReporteGenerado (de la feature 001, ya en memoria/disco tras excel_builder.py)
        │
        │ se sube a MinIO con key determinística
        ▼
ObjetoDeReporte (bucket + key + etag + generado_en)
        │
        │ referencia_archivo = bucket/key
        ▼
ReferenciaDeArchivo ──── se incluye en ────▶ evento reporte.listo (contrato de 001)
        │
        │ (tiempo después, según PoliticaDeRetencion)
        ▼
(eliminado por retencion.py, si supera dias_retencion y no está en descarga activa)
```

## Notas de integración con `001-worker-reportes`

- Esta feature consume la salida de `excel_builder.py` (archivo generado, ya sea en disco
  temporal o buffer streameable) como entrada directa de `persistencia.py`.
- El `solicitud_id` usado para la key ya existe como campo validado en
  `SolicitudDeReporte` (feature `001`); no se introduce ningún identificador nuevo.
- El campo `estado` (`generado`/`vacio`) del evento `reporte.listo`, definido en la
  feature `001`, es independiente de esta feature: un reporte "vacío" (sin datos en el
  rango) igualmente genera un archivo Excel válido (con encabezados) que se persiste
  siguiendo las mismas reglas.
