# Phase 0 Research: Persistencia de Reportes en MinIO

**Feature**: `002-minio-storage` | **Date**: 2026-09-15

> Nota: este documento fue revisado el 2026-09-15 tras la sesión de clarify del spec
> (ver spec.md → Clarifications). Las decisiones #4, #5 (numeración original), #6 y #7
> reflejan las respuestas ya confirmadas (sobrescritura sin verificación previa,
> retención 100% vía lifecycle rules, fallo de subida/integridad como falla transitoria
> sin reintento interno propio).

## Decisiones técnicas

### 1. Cliente MinIO: SDK oficial `minio` (Python)

**Decisión**: Usar el SDK oficial `minio` (compatible con la API S3), en vez de un
cliente S3 genérico como `boto3`.

**Rationale**: El SDK `minio` es más liviano, está mantenido por el propio proyecto
MinIO, y expone directamente `put_object`/`fput_object`/`get_object` con soporte nativo
de streaming, que es lo que necesitamos para FR-009 (no cargar el archivo completo en
memoria).

**Alternativas consideradas**: `boto3` (cliente S3 genérico de AWS) — funcional contra
MinIO por compatibilidad de API, pero agrega dependencias y configuración pensadas para
AWS (regiones, IAM) que no aplican aquí; se descarta por simplicidad (Principio VIII).

### 2. Derivación determinística de la key (FR-002, FR-006)

**Decisión**: `key = f"reportes/{anuncio_id}/{solicitud_id}.xlsx"`, usando el
`solicitud_id` (UUID, ya validado como clave de idempotencia en la feature `001`) como
componente único de la key, prefijado por `anuncio_id` para facilitar navegación/limpieza
manual si hiciera falta.

**Rationale**: Como `solicitud_id` ya es único por diseño (generado por `api-general`),
usarlo como key garantiza que la misma solicitud siempre resuelva al mismo objeto
(FR-002), y que un reintento de la misma solicitud sobrescriba o detecte el objeto
existente en vez de crear uno nuevo (FR-006), sin necesitar un mapeo adicional
solicitud→key en una tabla separada.

**Alternativas consideradas**: Key basada en un hash de `anuncio_id` + rango de fechas —
descartada porque dos solicitudes distintas para el mismo anuncio/rango (Edge Case del
spec) deben poder coexistir como objetos independientes; el `solicitud_id` ya resuelve
esto naturalmente al ser único por solicitud, no por combinación de parámetros.

### 3. Subida atómica (FR-005)

**Decisión**: Usar `put_object`/`fput_object` del SDK `minio` directamente sobre la key
final. La API de MinIO (como la de S3) solo hace visible el objeto una vez que el upload
completo termina exitosamente; si la conexión se corta a mitad de camino, no queda un
objeto parcial visible bajo esa key.

**Rationale**: Aprovechar la atomicidad nativa del protocolo S3/MinIO evita tener que
implementar un patrón manual de "subir a temporal + rename" (que en object storage no es
una operación atómica barata como en un filesystem). Se prioriza simplicidad (Principio
VIII) apoyándose en la garantía ya provista por la infraestructura.

**Alternativas consideradas**: Subir a una key temporal (`.tmp`) y copiar a la key final
al confirmar — descartado porque duplica el tráfico de red (copy interno) sin necesidad,
dado que `put_object` ya es atómico a nivel de visibilidad del objeto.

### 4. Verificación post-subida (FR-004)

**Decisión**: Tras subir, comparar el ETag/checksum devuelto por MinIO contra un hash
(MD5 o similar) calculado localmente del archivo antes de subir, y solo considerar la
persistencia exitosa si coinciden.

**Rationale**: Da una garantía verificable de integridad (SC-003: contenido idéntico
byte a byte) sin necesidad de descargar el archivo de vuelta para comparar.

**Alternativas consideradas**: Confiar ciegamente en que la subida sin excepción implica
integridad — más simple, pero no cumple con la exigencia explícita de verificación de
SC-003 en pruebas de integración.

### 5. Streaming de subida para archivos grandes (FR-009)

**Decisión**: Usar `put_object` pasando un stream/file-like object (el propio archivo
generado por `excel_builder.py` de la feature `001`, ya escrito a disco temporal o a un
buffer), en vez de cargar el contenido completo en un `bytes` en memoria antes de subir.

**Rationale**: El SDK `minio` soporta subir directamente desde un objeto file-like con
`length` conocido, delegando el chunking interno; esto es coherente con la decisión ya
tomada en la feature `001` de generar el Excel de forma incremental (streaming) a un
archivo temporal en disco.

**Alternativas consideradas**: Generar el Excel completo en memoria (`BytesIO`) y subirlo
— viable para reportes pequeños/medianos, pero contradice la decisión de streaming ya
tomada en `001-worker-reportes` para rangos de fechas sin límite (FR-011 de esa feature).

### 6. Política de retención y su metadata (FR-007, FR-008) — Clarification #2

**Decisión (revisada tras clarify)**: La retención se implementa **exclusivamente**
mediante **Lifecycle Rules nativas de MinIO** configuradas sobre el bucket/prefijo
`reportes/`, con expiración por antigüedad. No se implementa ningún job propio de
limpieza (`retencion.py`) en el código de este repo; la fecha de generación se guarda
igualmente como metadata del objeto (`x-amz-meta-generado-en`) a fines informativos/de
auditoría manual, pero no es leída por ningún proceso propio para decidir el borrado.

**Rationale**: Es la opción más simple (Principio VIII): delega completamente la lógica
de expiración a la infraestructura ya provista por MinIO, sin mantener un scheduler
propio, sin dependencia de `apscheduler`, y sin riesgo de que el job propio y las
lifecycle rules entren en conflicto o dupliquen trabajo.

**Alternativas consideradas**: Job propio en Python (`retencion.py`) como mecanismo
primario o como fallback — descartado explícitamente por Clarification #2; se prioriza
la simplicidad de un único mecanismo de verdad (las lifecycle rules) sobre la robustez
adicional que daría un fallback, dado que no fue solicitado como requisito.

**Impacto en Project Structure**: se elimina `src/worker/storage/retencion.py` y
`tests/integration/test_minio_retencion.py` (verificación de borrado automático) pasa a
ser un test de configuración de infraestructura, no de código propio — ver plan.md
actualizado.

### 7. No interferir con descargas en curso (FR-008)

**Decisión**: Al no existir un job propio de retención (ver decisión #6 revisada), no hay
ningún proceso de este repo que deba coordinarse con el webserver. La garantía de FR-008
recae enteramente en el modelo de consistencia de MinIO/S3: el webserver (feature `003`)
lee el objeto completo con una única llamada `get_object`, y una eliminación disparada
por la lifecycle rule nativa no corrompe una descarga ya en tránsito.

**Rationale**: Al eliminar el job propio, también se elimina la necesidad de cualquier
locking distribuido cross-feature, simplificando aún más esta decisión (Principio VIII).

**Alternativas consideradas**: Un mecanismo de "soft delete" con período de gracia
adicional antes del borrado físico — se deja como posible mejora futura, no como
requisito de esta iteración, dado que no fue pedido explícitamente y añade complejidad.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El bucket de MinIO no tiene lifecycle rules habilitadas en todos los entornos de despliegue | Se documenta como prerrequisito de infraestructura en `quickstart.md`; sin lifecycle rules configuradas, la retención (SC-004) simplemente no se cumple hasta que se configure — riesgo aceptado explícitamente tras Clarification #2, sin fallback propio |
| Reintentos concurrentes de la misma solicitud podrían intentar subir el mismo objeto en paralelo | La key determinística hace que ambas subidas converjan al mismo objeto final; se documenta como comportamiento aceptable (la última subida gana, ambas contienen el mismo contenido dado que provienen del mismo `solicitud_id` ya idempotente a nivel de generación en la feature `001`) |
| Verificación de integridad (checksum) agrega latencia | Se mide en Phase 1/implementación contra el objetivo de performance de la feature `001` (30s); si es significativo, se puede paralelizar el cálculo de hash con la subida |
| La verificación de integridad ahora es bloqueante (Clarification #4): un falso positivo de discrepancia de ETag bloquearía innecesariamente la publicación de `reporte.listo` | Usar el algoritmo de ETag estándar de MinIO/S3 (MD5 para objetos de una sola parte) para minimizar falsos positivos; cubierto con test de integración específico |
