# Phase 0 Research: Worker de Generación de Reportes

**Feature**: `001-worker-reportes` | **Date**: 2026-09-14

## Decisiones técnicas

### 1. Cliente de RabbitMQ: `pika`

**Decisión**: Usar `pika` en modo `BlockingConnection` con `channel.basic_qos(prefetch_count=N)`
para limitar mensajes en vuelo, combinado con un pool de workers internos (threads o
`asyncio` + `aio-pika` como alternativa si se prioriza concurrencia real).

**Rationale**: `pika` es la librería estándar de facto para RabbitMQ en Python y ya está
fijada en el stack de la constitution. El acknowledgement manual (`ack`/`nack`) es nativo
y permite implementar FR-007 (no confirmar hasta éxito completo) sin lógica adicional.

**Alternativas consideradas**:
- `aio-pika` (async nativo): más natural para FR-012 (concurrencia interna), pero agrega
  complejidad de runtime async en un worker que también hace I/O síncrono a SQL. Se
  evalúa como opción si el driver SQL elegido soporta async: en ese caso, `aio-pika` +
  `asyncpg` es preferible sobre `pika` + threads.
- Múltiples procesos consumidores (escalado horizontal): descartado explícitamente por
  clarification (FR-012) — se prioriza concurrencia dentro de una única instancia.

### 2. Concurrencia interna (FR-012, SC-004)

**Decisión**: Pool de tareas concurrentes (async con `asyncio` si el driver SQL usado es
async, o `ThreadPoolExecutor` si se usa un driver síncrono) con un límite configurable de
tareas simultáneas, correlacionado con `prefetch_count` de RabbitMQ para no sobrecargar
memoria ni conexiones a la DB.

**Rationale**: 50 solicitudes concurrentes (SC-004) es un volumen moderado, manejable sin
escalado horizontal, usando primitivas estándar de Python. Se prioriza simplicidad
(Principio VIII) sobre introducir infraestructura de orquestación (K8s HPA, múltiples
réplicas) que no fue pedida y complicaría el despliegue de un solo worker.

**Alternativas consideradas**: Escalado horizontal con múltiples réplicas del worker —
descartado por clarification explícita del usuario (Pregunta 5).

### 3. Generación de Excel: `openpyxl` en modo streaming

**Decisión**: Usar `openpyxl.Workbook(write_only=True)` con dos hojas (`Impresiones`,
`Clicks`), escribiendo filas de forma incremental a medida que se leen desde un cursor
SQL (server-side cursor / fetch en lotes), en vez de cargar todo el dataset en memoria.

**Rationale**: FR-011 exige soportar cualquier rango de fechas sin límite máximo,
procesando de forma incremental. El modo `write_only` de `openpyxl` está diseñado
exactamente para este caso (grandes volúmenes, bajo consumo de memoria), a costa de no
poder editar celdas ya escritas (aceptable: el reporte se genera de una sola pasada).

**Alternativas consideradas**:
- `xlsxwriter` con modo `constant_memory=True`: alternativa válida con capacidades
  similares; se prefiere `openpyxl` por ser la sugerencia explícita de la constitution
  ("openpyxl o similar") y tener más adopción/documentación.
- Pandas + `to_excel`: descartado para datasets grandes por cargar todo el DataFrame en
  memoria antes de escribir.

### 4. Consulta a la tabla `anuncio`: cursor server-side / paginación por lotes

**Decisión**: Usar un cursor de servidor (server-side cursor, si el motor SQL lo soporta
— PostgreSQL sí) o paginación por lotes (`LIMIT`/`OFFSET` o `keyset pagination` por
timestamp) para leer los registros de `anuncio` en bloques, en lugar de un único
`SELECT *` que traiga todo a memoria.

**Rationale**: Complementa la decisión de Excel streaming; sin esto, el streaming de
escritura no tendría efecto si la lectura ya carga todo en memoria.

**Alternativas consideradas**: Keyset pagination por timestamp se prefiere sobre
`OFFSET` puro para evitar degradación de performance en rangos muy grandes (offset alto
es costoso en PostgreSQL); se define como detalle de implementación en `data-model.md`.

### 5. Validación de payloads: `pydantic`

**Decisión**: Modelar `SolicitudDeReporte` (payload de `reporte.generar`) y
`ReporteGenerado` (payload de `reporte.listo`) como modelos `pydantic`, generados/
sincronizados a partir del schema JSON documentado en `api-general`.

**Rationale**: Permite validación estricta (FR-001, FR-002) con mensajes de error claros
para logging/dead-letter, y facilita mantener contract tests que comparen el modelo local
contra el schema fuente de verdad en `api-general`.

**Alternativas consideradas**: Validación manual con `jsonschema` puro — más verboso y
sin el beneficio de tipado estático que da `pydantic` para el resto del código.

### 6. Idempotencia: tabla de control de solicitudes procesadas

**Decisión**: Mantener una tabla propia (en la misma base de reportes, NO en `anuncio`)
que registre el UUID de solicitud ya procesado, con estado (`en_proceso`, `completado`) y
timestamp. Antes de procesar, el worker verifica si el UUID ya fue completado (idempotencia)
o está en proceso (evitar procesamiento paralelo duplicado del mismo evento redrivado).

**Rationale**: FR-008 exige idempotencia por UUID de solicitud generado por
`api-general`. Una tabla de control simple es más robusta que depender solo de
deduplicación en RabbitMQ (que no garantiza exactly-once) y es coherente con el
Principio II: esta tabla es propia de este repo, no compartida, por lo que no amplía la
excepción de aislamiento de datos.

**Alternativas consideradas**: Usar el nombre del objeto en MinIO como mecanismo de
idempotencia (verificar si ya existe) — descartado porque esta feature no incluye MinIO
(esa es la feature `002-minio-storage`); la idempotencia debe resolverse en esta capa
independientemente de la persistencia final.

### 7. Motor SQL de la base de reportes

**Decisión**: PostgreSQL, por ser el motor ya usado en el resto del sistema RecoMe
(DB General y DB Recomendaciones son PostgreSQL), facilitando consistencia operativa y
reduciendo la curva de aprendizaje/herramientas para el equipo.

**Rationale**: Aunque la spec deja el motor "a definir" (Assumptions), elegir un motor
ya validado a nivel de sistema reduce riesgo operativo y es compatible con acceso
concurrente de `api-general` sobre la misma tabla `anuncio` (Assumption del spec).

**Alternativas consideradas**: MySQL/MariaDB — descartado por no ser el estándar ya
adoptado en el resto de RecoMe; introduciría heterogeneidad de stack sin beneficio claro.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El schema de `reporte.generar`/`reporte.listo`/`anuncio` documentado en `api-general` aún no existe o cambia sin aviso | Contract tests que fallen explícitamente ante drift; comunicación activa con el equipo de `api-general` antes de implementar (Principio III) |
| Server-side cursors no soportados igual en todos los drivers SQL de Python | Se valida en Phase 1 con el driver elegido (`psycopg`/`asyncpg`) antes de implementar `repository.py` |
| Concurrencia interna (threads/async) puede complejizar el manejo de conexiones SQL/RabbitMQ compartidas | Usar pool de conexiones (SQLAlchemy engine pool o `asyncpg` pool) y una conexión de canal RabbitMQ por tarea/hilo, evitando compartir objetos no thread-safe |
