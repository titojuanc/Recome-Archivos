# Data Model: Webserver de Acceso Restringido a Reportes

**Feature**: `003-webserver-archivos`

## ReporteAutorizacion (nueva tabla, propia de este repo)

Persiste la asociación reporte → usuario autorizado, poblada por `001-worker-reportes`
tras una subida exitosa a MinIO (`002-minio-storage`), y consultada por el servicio de
autorización de este webserver en cada solicitud de descarga.

| Campo | Tipo | Constraints | Descripción |
|-------|------|-------------|-------------|
| `solicitud_id` | UUID | PK | Igual al `solicitud_id` de `SolicitudDeReporte` (001); identificador usado en la URL de descarga (Clarification #3) |
| `anuncio_id` | string | NOT NULL | Referencia informativa al anuncio del reporte (trazabilidad) |
| `usuario_solicitante` | string | NOT NULL | Usuario autorizado a descargar este reporte específico (debe coincidir con el claim `sub` del JWT) |
| `bucket` | string | NOT NULL | Bucket de MinIO donde vive el objeto (de `ReferenciaDeArchivo`, 002) |
| `key` | string | NOT NULL | Key del objeto en MinIO (de `ReferenciaDeArchivo`, 002) |
| `creado_en` | datetime (tz-aware) | NOT NULL, default now() | Momento de creación del registro (auditoría) |

**Reglas de validación**:
- `solicitud_id` es único (PK) — un reporte tiene exactamente un registro de autorización.
- Se inserta **solo** tras una subida exitosa a MinIO (si `subir_reporte()` falla, no se
  crea autorización para un archivo que no existe).
- No hay actualización de `usuario_solicitante` tras la creación: si se necesita cambiar
  el usuario autorizado, es un caso fuera de alcance de esta feature (ver Assumptions del
  spec: la autorización se origina en la solicitud original, no se reinterpreta).

**Relaciones**:
- 1:1 con la `SolicitudDeReporte` de `001-worker-reportes` (mismo `solicitud_id`).
- 1:1 conceptual con la `ReferenciaDeArchivo` de `002-minio-storage` (mismo
  `bucket`/`key`), aunque no hay FK física entre repos/módulos — se copian los valores al
  momento de la inserción para que este webserver no dependa de re-consultar el estado
  interno de `002`.

## SolicitudDeDescarga (concepto lógico, no persistido)

Representa un intento de acceso, modelado como la solicitud HTTP entrante a
`GET /reportes/{solicitud_id}` con header `Authorization: Bearer <JWT>`. No se persiste;
su resultado (200/403/404) es efímero por diseño (FR-005: sin caché de autorización).

| Campo | Origen | Descripción |
|-------|--------|-------------|
| `solicitud_id` | Path param de la URL | Identifica el reporte solicitado (Clarification #3) |
| `jwt` | Header `Authorization: Bearer <token>` | Credencial del usuario final |
| `usuario_solicitante` (derivado) | Claim `sub` del JWT, tras validar firma/expiración | Usuario que se compara contra `ReporteAutorizacion.usuario_solicitante` |

## Claims del JWT (contrato de autenticación, ver `research.md` §2)

| Claim | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `sub` | string | Sí | Identificador del usuario autorizado (debe coincidir con `usuario_solicitante`) |
| `exp` | int (unix timestamp) | Sí | Expiración del token; rechazado si venció |
| `iat` | int (unix timestamp) | No | Momento de emisión (informativo) |

## Estados de respuesta del servicio de autorización (`/auth`)

| Condición | Código | Efecto en Nginx |
|-----------|--------|------------------|
| JWT ausente, mal formado, firma inválida o expirado | `401` | Nginx responde `401` al cliente (rechazo de credenciales, FR-002) |
| JWT válido, pero `solicitud_id` no existe en `reporte_autorizacion` | `404` | Nginx responde `404` (FR-004) |
| JWT válido, `solicitud_id` existe, `sub` ≠ `usuario_solicitante` | `403` | Nginx responde `403` (FR-003) |
| JWT válido, `solicitud_id` existe, `sub` = `usuario_solicitante` | `200` (+ headers internos con `bucket`/`key`) | Nginx continúa con `X-Accel-Redirect` hacia MinIO |
