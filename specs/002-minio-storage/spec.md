# Feature Specification: Persistencia de Reportes Generados en MinIO

**Feature Branch**: `002-minio-storage`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description: "Persistencia de los archivos Excel generados por el worker de reportes en MinIO, incluyendo convenciones de nombrado/organización de objetos, y la referencia que se incluye en el evento reporte.listo para que el webserver pueda ubicar el archivo."

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
   se reintenta la generación para la misma solicitud, **Then** el objeto resultante sigue
   siendo único y válido (se sobrescribe de forma consistente o se detecta que ya existe y
   no se reprocesa la subida).
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

**Independent Test**: Se puede probar marcando reportes de prueba con fecha de generación
antigua y verificando que un proceso de limpieza los identifica y elimina, sin tocar
reportes recientes.

**Acceptance Scenarios**:

1. **Given** un reporte persistido hace más tiempo que el período de retención definido,
   **When** corre el proceso de limpieza, **Then** el objeto se elimina de MinIO.
2. **Given** un reporte persistido dentro del período de retención, **When** corre el
   proceso de limpieza, **Then** el objeto permanece intacto y accesible.

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
  al archivo originalmente generado (sin corrupción ni truncamiento).
- **FR-005**: El sistema MUST evitar que una subida fallida o parcial quede accesible como
  si fuera un objeto completo y válido.
- **FR-006**: El sistema MUST comportarse de forma idempotente ante reintentos de la misma
  solicitud: no debe generar objetos duplicados con ubicaciones distintas para la misma
  solicitud.
- **FR-007**: El sistema MUST aplicar una política de retención configurable que permita
  identificar y eliminar reportes cuya antigüedad supere el período definido.
- **FR-008**: El proceso de limpieza por retención MUST NOT eliminar ni corromper un
  objeto mientras está siendo servido activamente por el webserver.
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
