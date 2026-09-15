# Feature Specification: Worker de Generación de Reportes (Excel) + Modelo SQL de Anuncios

**Feature Branch**: `001-worker-reportes`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description: "Worker Python que consume el evento reporte.generar de RabbitMQ, consulta la tabla SQL anuncio (impresiones y clicks), transforma esos datos en un archivo Excel, y publica el evento reporte.listo con la referencia al archivo generado. Incluye el modelo de datos y acceso a la base SQL de reportes compartida con api-general."

## Clarifications

### Session 2026-09-14

- Q: ¿Cuál es la estructura esperada del archivo Excel generado? → A: Dos hojas
  separadas: una para impresiones y otra para clicks, cada una con sus propias columnas.
- Q: ¿Cómo se determina el identificador de solicitud usado para idempotencia? → A:
  `api-general` genera un UUID único por solicitud y lo incluye en el payload de
  `reporte.generar`; el worker lo usa tal cual como clave de idempotencia.
- Q: ¿Cómo debe manejarse un registro de `anuncio` con datos incompletos o corruptos
  dentro del rango solicitado? → A: Se incluye en el Excel, pero con un valor especial
  (p. ej. "N/D") en el/los campos faltantes o inválidos, en lugar de excluirlo o
  inventar un valor.
- Q: ¿Hay un límite máximo de rango de fechas que el worker deba rechazar? → A: No hay
  límite máximo; el worker MUST soportar cualquier rango de fechas mediante
  procesamiento incremental (streaming/paginado) de la consulta y de la escritura del
  Excel.
- Q: ¿Cómo se sostiene la concurrencia de 50 solicitudes simultáneas (SC-004)? → A: Una
  única instancia del worker procesa mensajes de forma concurrente internamente
  (async/threads), sin depender de escalado horizontal por múltiples instancias.
- Q: ¿Cómo conviven el filtro por rango de fechas (FR-003) con la inclusión de registros
  de `timestamp` nulo/corrupto (FR-010)? → A: Los registros del anuncio solicitado con
  `timestamp` nulo/corrupto se incluyen siempre en el Excel, independientemente del rango
  de fechas pedido, marcando el campo como "N/D" (no se puede determinar si caen dentro
  del rango, así que no se excluyen por el filtro).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generar un reporte Excel a partir de un pedido válido (Priority: P1)

Un usuario, a través de `api-general`, solicita un reporte de desempeño para un anuncio
específico. `api-general` publica el evento `reporte.generar` con la información
necesaria (identificador del anuncio, rango de fechas, usuario solicitante). El worker de
este módulo consume el evento, consulta las impresiones y clicks del anuncio en la tabla
`anuncio`, arma un archivo Excel legible con esos datos, y publica el evento
`reporte.listo` con la referencia al archivo generado (sin exponerlo aún — eso es de otra
feature).

**Why this priority**: Es el flujo central del módulo; sin esto no existe el producto.
Todo lo demás (MinIO, webserver) depende de que este flujo funcione primero.

**Independent Test**: Se puede probar publicando manualmente un evento `reporte.generar`
válido contra una cola de test, verificando que el worker consulta correctamente los
datos de `anuncio`, genera un archivo Excel con el contenido esperado, y publica
`reporte.listo` con la referencia correcta — todo sin necesidad de MinIO ni webserver
reales (se puede mockear la persistencia del archivo).

**Acceptance Scenarios**:

1. **Given** un evento `reporte.generar` válido con un `anuncio_id` que tiene impresiones
   y clicks registrados, **When** el worker lo procesa, **Then** se genera un archivo
   Excel con una fila por cada evento de impresión/click dentro del rango solicitado, y se
   publica `reporte.listo` referenciando ese archivo.
2. **Given** un evento `reporte.generar` válido con un `anuncio_id` que no tiene ninguna
   impresión ni click registrado en el rango solicitado, **When** el worker lo procesa,
   **Then** se genera igualmente un archivo Excel válido (vacío o con encabezados
   solamente) y se publica `reporte.listo` indicando que el reporte no tiene datos.
3. **Given** un evento `reporte.generar` correctamente formado, **When** el worker termina
   de procesarlo exitosamente, **Then** el mensaje se confirma (ack) en la cola y no se
   reprocesa.

---

### User Story 2 - Rechazar eventos inválidos o mal formados (Priority: P2)

El worker recibe un evento `reporte.generar` que no cumple con el schema documentado en
`api-general` (por ejemplo, falta el `anuncio_id`, el rango de fechas es inválido, o el
tipo de dato de un campo es incorrecto). El worker debe rechazar el evento sin intentar
adivinar valores por defecto, y sin generar un reporte parcial o inconsistente.

**Why this priority**: Es crítico para la integridad de los reportes generados y para no
propagar errores silenciosos hacia `api-general`, pero depende de que el flujo feliz (User
Story 1) ya esté definido como referencia de qué es "válido".

**Independent Test**: Se puede probar publicando eventos deliberadamente inválidos (campos
faltantes, tipos incorrectos, `anuncio_id` inexistente) y verificando que el worker no
genera ningún archivo, no publica `reporte.listo`, y enruta el mensaje a dead-letter o lo
rechaza explícitamente.

**Acceptance Scenarios**:

1. **Given** un evento `reporte.generar` sin `anuncio_id`, **When** el worker lo recibe,
   **Then** el evento se rechaza (nack) y se enruta a dead-letter, sin generar archivo ni
   publicar `reporte.listo`.
2. **Given** un evento `reporte.generar` con un rango de fechas inválido (fecha de inicio
   posterior a la de fin), **When** el worker lo recibe, **Then** el evento se rechaza de
   la misma forma.
3. **Given** un evento `reporte.generar` con un `anuncio_id` que no existe en la tabla
   `anuncio`, **When** el worker lo procesa, **Then** el evento se rechaza (no se genera un
   reporte vacío disfrazado de válido; se distingue explícitamente de la User Story 1
   Scenario 2, donde el anuncio existe pero no tiene datos en el rango).

---

### User Story 3 - Recuperación ante fallos transitorios (Priority: P3)

El worker pierde conectividad momentánea con la base de datos de reportes o con RabbitMQ
mientras procesa un evento. El sistema debe poder reintentar el procesamiento sin duplicar
reportes ni perder el evento original.

**Why this priority**: Mejora la robustez operativa, pero el sistema ya entrega valor
completo con las User Stories 1 y 2 funcionando; esta es una mejora de resiliencia sobre
la base ya construida.

**Independent Test**: Se puede probar simulando una caída de conexión a la base de datos
durante el procesamiento de un evento y verificando que el evento no se pierde (no se
hace ack antes de confirmar éxito) y que un reintento posterior completa el procesamiento
correctamente sin generar un reporte duplicado.

**Acceptance Scenarios**:

1. **Given** un evento `reporte.generar` válido, **When** la conexión a la base de datos
   de reportes falla durante la consulta, **Then** el worker no confirma (ack) el mensaje
   y este queda disponible para reintento.
2. **Given** un evento que fue reintentado tras una falla transitoria, **When** el worker
   lo procesa exitosamente en el segundo intento, **Then** se genera un único reporte y se
   publica un único evento `reporte.listo` (no hay duplicación).

### Edge Cases

- ¿Qué pasa si `api-general` publica dos veces el mismo `reporte.generar` (mismo
  identificador de solicitud) por un reintento propio de `api-general`? El worker debe
  poder identificar duplicados y evitar generar dos reportes idénticos.
- ¿Qué pasa si el rango de fechas solicitado es extremadamente amplio (por ejemplo, varios
  años) y el volumen de filas de `anuncio` es muy grande? El worker debe poder generarlo
  sin agotar memoria (streaming o paginado de la consulta/escritura del Excel).
- ¿Qué pasa si el schema de `reporte.generar` documentado en `api-general` cambia
  (agrega o quita un campo) sin que este repo haya actualizado su validación? El worker
  debe rechazar los eventos que no calcen con la versión de schema que tiene implementada,
  en vez de procesarlos parcialmente.
- ¿Qué pasa si la tabla `anuncio` tiene registros con datos corruptos o nulos en campos
  esperados (por ejemplo, timestamp de impresión nulo)? El worker debe incluir el
  registro en el Excel marcando el campo afectado con un valor especial (p. ej. "N/D"),
  sin excluirlo ni fallar todo el reporte.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El worker MUST consumir eventos `reporte.generar` desde la cola de RabbitMQ
  correspondiente, validando cada evento contra el schema documentado en `api-general`
  antes de procesarlo.
- **FR-002**: El worker MUST rechazar (nack/dead-letter) cualquier evento `reporte.generar`
  que no cumpla el schema documentado, sin completar campos faltantes con valores por
  defecto.
- **FR-003**: El worker MUST consultar la tabla `anuncio` (impresiones y clicks) filtrando
  por el `anuncio_id` y el rango de fechas indicados en el evento recibido, incluyendo
  además, sin excepción, todo registro del mismo `anuncio_id` cuyo `timestamp` sea nulo o
  no interpretable (ver FR-010), independientemente de si cae o no dentro del rango.
- **FR-004**: El worker MUST generar un archivo Excel legible con dos hojas separadas —
  una de impresiones y otra de clicks del anuncio solicitado — cada una con sus propias
  columnas relevantes (timestamp del evento y metadata básica disponible en `anuncio`),
  incluso cuando no haya datos en el rango (hojas con encabezados solamente, reporte
  vacío).
- **FR-005**: El worker MUST rechazar el evento (no generar un reporte "vacío" silencioso)
  cuando el `anuncio_id` referenciado no exista en la tabla `anuncio`.
- **FR-006**: El worker MUST publicar el evento `reporte.listo` únicamente después de
  generar el archivo Excel exitosamente, incluyendo la referencia necesaria para que un
  paso posterior (persistencia en MinIO) pueda ubicar y almacenar ese archivo.
- **FR-007**: El worker MUST confirmar (ack) un mensaje de `reporte.generar` únicamente
  después de completar exitosamente la generación del reporte y la publicación de
  `reporte.listo`; en caso de fallo transitorio, el mensaje MUST permanecer disponible
  para reintento.
- **FR-008**: El worker MUST evitar generar reportes duplicados ante el reprocesamiento
  del mismo evento, usando como clave de idempotencia el identificador único de solicitud
  (UUID) generado por `api-general` e incluido en el payload de `reporte.generar`.
- **FR-009**: El acceso a la tabla `anuncio` MUST respetar el esquema compartido con
  `api-general` documentado centralmente; el worker no MUST asumir columnas o estructuras
  no documentadas.
- **FR-010**: El worker MUST incluir en el Excel todo registro de `anuncio` dentro del
  rango solicitado, incluso si tiene campos incompletos o corruptos; en esos casos MUST
  marcar el/los campos afectados con un valor especial (p. ej. "N/D") en lugar de
  excluir el registro o inventar un valor, sin abortar la generación completa del reporte
  por un registro individual defectuoso. En particular, un registro con `timestamp`
  nulo/no interpretable MUST incluirse siempre (no se excluye por no poder evaluarse
  contra el rango de fechas), marcando ese campo como "N/D".
- **FR-011**: El worker MUST soportar cualquier rango de fechas, sin imponer un límite
  máximo, procesando la consulta y/o la escritura del Excel de forma incremental
  (streaming/paginado) cuando el volumen de datos lo requiera, sin agotar memoria.
- **FR-012**: El worker MUST procesar múltiples solicitudes de reporte de forma
  concurrente dentro de una única instancia (async/threads), sin requerir escalado
  horizontal (múltiples instancias) para sostener la carga esperada.

### Key Entities

- **SolicitudDeReporte** (payload del evento `reporte.generar`): representa el pedido de
  un reporte; incluye como mínimo un identificador único de solicitud (UUID generado por
  `api-general`, usado como clave de idempotencia), el identificador del anuncio, el
  rango de fechas solicitado, y el usuario solicitante (para la validación de acceso
  posterior, fuera de alcance de este worker).
- **Anuncio** (tabla `anuncio`, compartida con `api-general`): representa un anuncio del
  sistema y sus eventos de interacción — impresiones y clicks — con sus timestamps
  asociados. El schema exacto de esta tabla se documenta y coordina con `api-general`.
- **ReporteGenerado** (payload del evento `reporte.listo`): representa el resultado de la
  generación; incluye la referencia al archivo generado y el identificador de la solicitud
  original que le dio origen, para que `api-general` pueda correlacionarlo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El worker procesa un evento `reporte.generar` válido y publica el
  correspondiente `reporte.listo` en menos de 30 segundos para anuncios con hasta 100.000
  registros de impresiones/clicks en el rango solicitado.
- **SC-002**: El 100% de los eventos `reporte.generar` que no cumplen el schema
  documentado son rechazados sin generar ningún archivo ni publicar `reporte.listo`.
- **SC-003**: Ante un reintento del mismo evento (mismo identificador de solicitud), el
  sistema nunca genera más de un reporte para esa solicitud.
- **SC-004**: El worker sostiene el procesamiento concurrente de al menos 50 solicitudes
  de reporte en una única instancia (sin escalado horizontal) sin pérdida de eventos ni
  caída del proceso.

## Assumptions

- `api-general` es responsable de validar que el usuario solicitante tiene permiso para
  ver el anuncio solicitado antes de publicar `reporte.generar`; este worker no revalida
  permisos de negocio, solo procesa el pedido recibido.
- El schema de `reporte.generar`, `reporte.listo` y de la tabla `anuncio` ya están (o
  estarán) documentados en el repo `api-general` como fuente única de verdad; esta feature
  asume que existe o existirá esa documentación como contrato a validar.
- La persistencia física del archivo Excel generado (en MinIO) y su exposición vía
  webserver son features separadas y posteriores; esta feature entrega el archivo
  generado y la referencia lógica necesaria, pero no implementa el almacenamiento final
  ni el acceso HTTP al archivo.
- El motor SQL concreto para la base de reportes no se decide en esta spec (se define en
  la fase de plan/implementación), pero se asume compatibilidad con acceso concurrente
  de lectura desde `api-general` sobre la misma tabla `anuncio`.
- El volumen típico de un reporte individual es acotado (miles a cientos de miles de
  filas), no se asume la necesidad de procesamiento distribuido tipo big data.

