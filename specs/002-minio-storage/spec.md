# Feature Specification: Persistencia de Reportes Generados en MinIO

**Feature Branch**: `002-minio-storage`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description: "Persistencia de los archivos Excel generados por el worker de reportes en MinIO, incluyendo convenciones de nombrado/organización de objetos, y la referencia que se incluye en el evento reporte.listo para que el webserver pueda ubicar el archivo."

## Clarifications

### Session 2026-09-15

- Q: Ante un reintento de la misma solicitud (US2, Scenario 1), ¿cómo debe comportarse la
  subida si el objeto ya existe en MinIO? → A: Subir siempre sin verificar existencia
  previa, dejando que MinIO sobrescriba el objeto existente (mismo `solicitud_id` implica
  mismo contenido esperado; la sobrescritura es inofensiva y evita una llamada extra de
  verificación antes de cada subida).
- Q: ¿Cuál es el mecanismo primario de la política de retención (FR-007)? → A:
  Únicamente lifecycle rules nativas de MinIO (configuración de infraestructura sobre el
  bucket/prefijo), sin implementar un job de limpieza propio en el código de este repo.
- Q: ¿Qué debe hacer el sistema si la subida a MinIO (`put_object`) falla (ej. red
  cortada)? → A: Tratarlo como falla transitoria: no marcar la solicitud como
  completada y propagar la excepción, delegando el reintento completo (regenerar Excel +
  resubir) al mecanismo de idempotencia/reintento ya definido en `001-worker-reportes`
  (User Story 3 de esa feature), sin lógica de reintento interno propia en esta capa.
- Q: ¿La verificación de integridad post-subida (ETag vs. checksum local, FR-004) es
  bloqueante? → A: Sí, bloqueante: si el ETag no coincide con el checksum local
  calculado antes de subir, se trata como fallo de persistencia (misma ruta que FR-005:
  no se marca la solicitud como completada, se propaga como falla transitoria).
- Q: ¿Cómo se verifica que la retención (SC-004, vía lifecycle rules nativas) funciona
  correctamente? → A: Únicamente con un test de integración que configura la lifecycle
  rule sobre un prefijo de prueba y confirma la eliminación esperada; no se implementa
  auditoría operativa continua en producción como parte de esta feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Persistir un reporte generado de forma recuperable (Priority: P1)

Una vez que el worker termina de generar un archivo Excel a partir de los datos de
`anuncio` (ver feature `001-worker-reportes`), ese archivo debe quedar almacenado de
forma durable en MinIO, con una ubicación (bucket/objeto) determinística y recuperable a
partir de los datos de la solicitud original, para que un componente posterior (el
webserver) pueda ubicarlo sin ambigüedad.

**Why this priority**: Sin persistencia durable no hay nada que exponer después; es el
segundo eslabón obligatorio de la cadena worker → storage → webserver.

**Independent Test**: Se puede probar tomando un archivo Excel ya generado (mockeando la
feature 001) y verificando que se sube a MinIO en la ubicación esperada, que el objeto es
recuperable con esa misma ubicación, y que la referencia devuelta es la que luego viaja
en el evento `reporte.listo`.

**Acceptance Scenarios**:

1. **Given** un archivo Excel generado exitosamente para una solicitud con identificador
   conocido, **When** se persiste en MinIO, **Then** el objeto queda accesible en una
   ubicación derivada de forma determinística de esa solicitud (mismo identificador →
   misma ubicación).
2. **Given** un archivo ya persistido en MinIO, **When** se solicita su recuperación con la
   referencia devuelta al momento de guardarlo, **Then** el contenido recuperado es
   idéntico (byte a byte) al generado originalmente.
3. **Given** una persistencia exitosa en MinIO, **When** el worker continúa el flujo,
   **Then** la referencia al objeto (bucket + key, o URL interna) se incluye en el payload
   del evento `reporte.listo`.

---

### User Story 2 - Evitar sobrescritura o pérdida ante reintentos (Priority: P2)

Si el worker reintenta la generación de un reporte (por ejemplo, tras una falla
transitoria descrita en la feature `001-worker-reportes`), la persistencia en MinIO no
debe generar objetos duplicados con nombres distintos ni corromper un objeto ya subido
correctamente.

**Why this priority**: Da consistencia al mecanismo de idempotencia ya definido a nivel de
worker; depende de que la convención de nombrado (User Story 1) ya exista.

**Independent Test**: Se puede probar subiendo el mismo archivo dos veces con el mismo
identificador de solicitud y verificando que el resultado final es un único objeto
consistente, no dos objetos ni un objeto corrupto por escritura concurrente/parcial.

**Acceptance Scenarios**:

1. **Given** una solicitud cuyo reporte ya fue persistido exitosamente en MinIO, **When**
   se reintenta la generación para la misma solicitud, **Then** la subida sobrescribe el
   objeto existente en la misma ubicación determinística, sin verificación previa de
   existencia, resultando en un único objeto válido.
2. **Given** una subida a MinIO que falla a mitad de camino (conexión cortada), **When** el
   sistema reintenta, **Then** no queda un objeto parcialmente escrito accesible como si
   estuviera completo.

---

### User Story 3 - Retención y limpieza de reportes antiguos (Priority: P3)

Los reportes generados no deben acumularse indefinidamente en MinIO sin control; debe
existir una política de retención que permita eventualmente eliminar u archivar reportes
antiguos sin afectar a los que están vigentes o en proceso de ser descargados.

**Why this priority**: Es una mejora operativa/de costo sobre una base ya funcional; el
sistema entrega valor completo (Stories 1 y 2) sin esto, pero crecer sin límite no es
sostenible a largo plazo.

**Independent Test**: Se puede probar configurando una lifecycle rule de expiración corta
sobre un prefijo de prueba, subiendo un objeto con esa antigüedad simulada (o esperando el
período configurado), y verificando que MinIO lo elimina automáticamente sin intervención
manual, mientras un objeto reciente en el mismo prefijo permanece intacto.

**Acceptance Scenarios**:

1. **Given** un reporte persistido hace más tiempo que el período de retención definido
   en la lifecycle rule del bucket/prefijo, **When** MinIO evalúa la regla (proceso
   interno de MinIO, sin intervención de este repo), **Then** el objeto se elimina
   automáticamente.
2. **Given** un reporte persistido dentro del período de retención, **When** MinIO evalúa
   la lifecycle rule, **Then** el objeto permanece intacto y accesible.

### Edge Cases

- ¿Qué pasa si MinIO no está disponible al momento en que el worker intenta persistir el
  archivo? El worker no debe publicar `reporte.listo` con una referencia inválida; debe
  tratarse como una falla transitoria (ver feature `001-worker-reportes`, User Story 3).
- ¿Qué pasa si dos solicitudes distintas (identificadores de solicitud diferentes) piden
  reportes para el mismo `anuncio_id` y mismo rango de fechas? Cada una debe generar y
  persistir su propio objeto independiente, sin colisionar en la misma ubicación.
- ¿Qué pasa si el archivo generado supera un tamaño considerable? La subida a MinIO debe
  poder manejarse sin cargar necesariamente todo el archivo en memoria de una sola vez.
- ¿Qué pasa si se solicita eliminar (retención) un reporte que está siendo descargado en
  ese mismo instante a través del webserver? La política de limpieza no debe interrumpir
  una descarga en curso de forma abrupta e inconsistente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST persistir en MinIO cada archivo Excel generado exitosamente
  por el worker de reportes.
- **FR-002**: El sistema MUST derivar la ubicación (bucket/key) del objeto en MinIO de
  forma determinística a partir del identificador de la solicitud de reporte original,
  de forma que la misma solicitud siempre resuelva a la misma ubicación.
- **FR-003**: El sistema MUST incluir la referencia al objeto persistido (bucket + key, o
  URL/identificador interno equivalente) en el payload del evento `reporte.listo`.
- **FR-004**: El sistema MUST garantizar que el contenido recuperado de MinIO sea idéntico
  al archivo originalmente generado (sin corrupción ni truncamiento), verificando de forma
  bloqueante que el ETag devuelto por MinIO coincide con un checksum calculado localmente
  antes de subir; si no coincide, MUST tratarse como fallo de persistencia (misma ruta que
  FR-005).
- **FR-005**: El sistema MUST evitar que una subida fallida o parcial quede accesible como
  si fuera un objeto completo y válido, apoyándose en la atomicidad nativa de la subida a
  MinIO; ante una excepción durante la subida, el sistema MUST NOT marcar la solicitud
  como completada y MUST propagar el fallo como una falla transitoria, delegando el
  reintento (regeneración y resubida completa) al mecanismo de idempotencia de
  `001-worker-reportes`, sin implementar reintentos internos propios en esta capa.
- **FR-006**: El sistema MUST comportarse de forma idempotente ante reintentos de la misma
  solicitud: la subida MUST sobrescribir directamente el objeto en su ubicación
  determinística (sin verificar existencia previa), de forma que nunca se generen objetos
  duplicados con ubicaciones distintas para la misma solicitud.
- **FR-007**: El sistema MUST aplicar una política de retención configurable mediante
  lifecycle rules nativas de MinIO sobre el bucket/prefijo de reportes, sin requerir un
  proceso de limpieza propio en el código de este repo.
- **FR-008**: La configuración de lifecycle rules MUST evitar eliminar u corromper un
  objeto mientras está siendo servido activamente por el webserver, apoyándose en el
  modelo de consistencia de MinIO/S3 para descargas ya en curso (ver research.md).
- **FR-009**: El sistema MUST soportar la persistencia de archivos de tamaño considerable
  sin requerir cargar el archivo completo en memoria en un único bloque.
- **FR-010**: El acceso a MinIO (credenciales, bucket) MUST estar acotado a los
  componentes de este repo (worker y webserver); ningún otro repo del sistema accede
  directamente a MinIO.

### Key Entities

- **ObjetoDeReporte**: representa el archivo Excel persistido en MinIO; se identifica por
  una ubicación determinística (bucket + key) derivada del identificador de la solicitud
  de reporte, y tiene una fecha de generación relevante para la política de retención.
- **ReferenciaDeArchivo** (parte del payload de `reporte.listo`): representa el puntero
  lógico al `ObjetoDeReporte`, suficiente para que el webserver (feature siguiente) pueda
  ubicarlo y servirlo sin necesitar más contexto.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los reportes generados exitosamente por el worker quedan
  persistidos en MinIO antes de que se publique el evento `reporte.listo`.
- **SC-002**: Ante un reintento de la misma solicitud de reporte, nunca se generan más de
  un objeto válido en MinIO para esa solicitud.
- **SC-003**: El contenido descargado de un objeto persistido coincide byte a byte con el
  archivo generado originalmente, verificado en el 100% de las pruebas de integración.
- **SC-004**: Los reportes que superan el período de retención configurado se eliminan
  dentro de un ciclo de limpieza posterior a su vencimiento, sin intervención manual.

## Assumptions

- La política de retención concreta (cuántos días se conservan los reportes) es un
  parámetro de configuración a definir en la fase de plan/implementación, no un valor fijo
  de esta spec.
- El bucket o los buckets de MinIO usados por este módulo son de uso exclusivo de este
  repo; ningún otro repo del sistema lee o escribe directamente sobre ellos (ver
  Principio I y II de la constitution).
- La convención de nombrado de objetos puede incluir el identificador de solicitud y/o el
  `anuncio_id`, pero el detalle exacto del esquema de keys se define en el plan técnico,
  no en esta spec.
- Esta feature no implementa el acceso HTTP restringido a los archivos (eso corresponde a
  la feature del webserver); solo garantiza que el archivo está disponible y referenciado
  correctamente para que el webserver lo pueda servir después.
