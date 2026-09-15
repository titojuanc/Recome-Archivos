# Feature Specification: Webserver de Acceso Restringido a Reportes

**Feature Branch**: `003-webserver-archivos`

**Created**: 2026-09-14

**Status**: Draft

**Input**: User description: "Webserver que expone los reportes Excel persistidos en MinIO, con acceso restringido al usuario indicado en la solicitud original, controlado en exclusiva por este repo, sin acceso público anónimo."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Descargar un reporte propio con acceso autorizado (Priority: P1)

Un usuario final, habiendo recibido (a través de `api-general`, fuera de este repo) la
URL de acceso a su reporte, intenta descargar el archivo Excel correspondiente. El
webserver debe verificar que quien solicita la descarga es efectivamente el usuario
autorizado para ese reporte específico, y en ese caso, servir el archivo desde MinIO.

**Why this priority**: Es el propósito final de todo el módulo: sin esto, generar y
persistir el reporte no tiene valor de cara al usuario. Depende de que las features
`001-worker-reportes` y `002-minio-storage` ya existan.

**Independent Test**: Se puede probar generando/persistiendo un reporte de prueba en MinIO
(mockeando las features anteriores) con un usuario autorizado conocido, solicitando la
descarga con las credenciales de ese usuario, y verificando que el contenido devuelto
coincide con el objeto persistido.

**Acceptance Scenarios**:

1. **Given** un reporte persistido en MinIO asociado a un usuario autorizado conocido,
   **When** ese usuario solicita la descarga con sus credenciales válidas, **Then** el
   webserver responde con el contenido del archivo Excel correspondiente.
2. **Given** un reporte persistido y una URL de acceso válida, **When** transcurre un
   tiempo razonable y el usuario autorizado vuelve a solicitar el mismo reporte, **Then**
   el webserver sigue permitiendo el acceso mientras el reporte no haya sido eliminado por
   la política de retención (feature `002-minio-storage`).

---

### User Story 2 - Rechazar acceso no autorizado (Priority: P1)

Un usuario distinto al indicado como autorizado para un reporte específico (o una
solicitud sin credenciales válidas) intenta acceder a la URL de descarga de ese reporte.
El webserver debe rechazar el acceso sin revelar información sobre el contenido o
existencia del reporte más allá de lo estrictamente necesario.

**Why this priority**: Es igual de crítico que la User Story 1 — el acceso restringido es
la razón de ser de este componente (Principio V de la constitution); sin este control, el
webserver expondría archivos de forma efectivamente pública.

**Independent Test**: Se puede probar solicitando la descarga de un reporte de prueba con
credenciales de un usuario distinto al autorizado, o sin credenciales, y verificando que
la respuesta es un rechazo (no autorizado / no encontrado) y que el contenido del archivo
nunca se transmite.

**Acceptance Scenarios**:

1. **Given** un reporte asociado a un usuario autorizado A, **When** un usuario B (o una
   solicitud anónima) intenta descargarlo, **Then** el webserver rechaza la solicitud sin
   entregar el contenido del archivo.
2. **Given** una solicitud sin credenciales de ningún tipo, **When** se intenta acceder a
   cualquier URL de reporte, **Then** el webserver rechaza el acceso de forma consistente
   (nunca hay acceso público anónimo).
3. **Given** una solicitud con credenciales inválidas o expiradas, **When** se intenta
   acceder a un reporte, **Then** el webserver rechaza el acceso.

---

### User Story 3 - Manejar reportes inexistentes o ya eliminados (Priority: P2)

Un usuario (autorizado o no) intenta acceder a una URL de reporte que ya no existe,
porque fue eliminado por la política de retención (feature `002-minio-storage`) o porque
la referencia es inválida/mal formada.

**Why this priority**: Es un caso de robustez sobre el flujo principal; mejora la
experiencia y evita comportamientos inconsistentes, pero el sistema ya es funcionalmente
completo con las User Stories 1 y 2.

**Independent Test**: Se puede probar solicitando una URL con un identificador de reporte
inexistente o correspondiente a un objeto ya eliminado de MinIO, y verificando que el
webserver responde de forma clara (no encontrado) sin exponer detalles internos de MinIO.

**Acceptance Scenarios**:

1. **Given** una URL de reporte cuyo objeto ya fue eliminado por retención, **When** se
   solicita la descarga (incluso con credenciales válidas del usuario originalmente
   autorizado), **Then** el webserver responde indicando que el reporte ya no está
   disponible.
2. **Given** una URL de reporte mal formada o con un identificador inexistente, **When**
   se solicita, **Then** el webserver responde con un error claro sin filtrar información
   interna de la estructura de MinIO.

### Edge Cases

- ¿Qué pasa si el usuario autorizado cambia sus credenciales (por ejemplo, se le revoca el
  acceso) después de que el reporte fue generado pero antes de que lo descargue? El
  webserver debe validar la autorización vigente al momento de cada solicitud, no solo al
  momento de la generación.
- ¿Qué pasa si se realizan múltiples solicitudes de descarga concurrentes del mismo
  reporte por el mismo usuario autorizado? Todas deben poder completarse correctamente sin
  interferir entre sí.
- ¿Qué pasa si MinIO no responde momentáneamente mientras el webserver intenta servir un
  archivo cuyo acceso ya fue autorizado? El webserver debe informar un error transitorio
  sin filtrar detalles internos, y no debe "cachear" una autorización como si el archivo
  ya se hubiera entregado.
- ¿Qué pasa si el mismo reporte es solicitado con un método de acceso que intenta evitar
  la validación (por ejemplo, adivinando o enumerando URLs)? El esquema de acceso debe ser
  resistente a enumeración (identificadores no predecibles/secuenciales).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El webserver MUST validar, en cada solicitud de descarga, que el
  solicitante es el usuario indicado como autorizado para ese reporte específico, antes de
  servir cualquier contenido.
- **FR-002**: El webserver MUST rechazar toda solicitud sin credenciales válidas; MUST NOT
  existir ningún modo de acceso público/anónimo a un reporte.
- **FR-003**: El webserver MUST rechazar solicitudes de un usuario distinto al autorizado
  para un reporte determinado, sin exponer contenido ni metadata sensible del archivo.
- **FR-004**: El webserver MUST responder de forma clara y sin filtrar detalles internos de
  MinIO cuando el reporte solicitado no existe o ya fue eliminado por la política de
  retención.
- **FR-005**: El webserver MUST validar la autorización vigente en cada solicitud
  individual, no basarse en un estado de autorización cacheado de una solicitud anterior.
- **FR-006**: El esquema de identificadores/URLs de acceso a reportes MUST ser resistente a
  enumeración (no debe ser trivial adivinar la URL de un reporte ajeno a partir de una
  propia).
- **FR-007**: El webserver MUST servir el contenido leyéndolo desde MinIO (el bucket
  exclusivo de este repo, ver feature `002-minio-storage`); MUST NOT mantener una copia
  independiente y potencialmente desincronizada del archivo.
- **FR-008**: El webserver MUST informar un error transitorio (sin exponer contenido) si
  MinIO no está disponible al momento de intentar servir un archivo ya autorizado.
- **FR-009**: El control de configuración de acceso del webserver (qué usuario puede
  acceder a qué reporte) MUST estar bajo control exclusivo de este repo; ningún otro
  módulo administra ni despliega este webserver.
- **FR-010**: El webserver MUST soportar múltiples solicitudes concurrentes de descarga
  del mismo reporte por el mismo usuario autorizado sin errores de interferencia entre
  solicitudes.

### Key Entities

- **SolicitudDeDescarga**: representa un intento de acceso a un reporte específico;
  incluye la identidad del solicitante (credenciales) y la referencia al reporte
  solicitado.
- **AutorizacionDeReporte**: representa la asociación entre un reporte generado (feature
  `001-worker-reportes` / `002-minio-storage`) y el usuario indicado como autorizado a
  descargarlo; esta autorización se valida en cada solicitud.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las solicitudes de descarga sin credenciales válidas son
  rechazadas, sin excepción, en las pruebas de acceso.
- **SC-002**: El 100% de las solicitudes de un usuario no autorizado para un reporte
  específico son rechazadas sin exponer el contenido del archivo.
- **SC-003**: Un usuario autorizado puede descargar su reporte exitosamente en el 100% de
  los intentos mientras el archivo exista en MinIO y su autorización siga vigente.
- **SC-004**: Las solicitudes sobre reportes eliminados por retención responden de forma
  consistente (no encontrado / ya no disponible) en el 100% de los casos, sin exponer
  detalles internos de MinIO.

## Assumptions

- La identidad/credenciales del usuario final para validar el acceso son provistas o
  verificables a través de un mecanismo ya existente en el sistema (por ejemplo, un token
  emitido en última instancia por `api-general`); este módulo no implementa un sistema de
  autenticación de usuarios propio ni gestiona altas de usuarios.
- La asociación reporte→usuario autorizado se origina en la información ya presente en la
  solicitud original (`SolicitudDeReporte` de la feature `001-worker-reportes`); esta
  feature no redefine ni reinterpreta quién es el usuario autorizado.
- El mecanismo concreto (JWT, cookie de sesión, API key firmada, URL prefirmada con
  expiración, etc.) para validar al usuario se decide en la fase de plan/implementación,
  no en esta spec.
- Este webserver no es alcanzable directamente por los frontends del sistema como puerta
  de entrada general; el flujo por el cual el usuario obtiene la URL/credencial de acceso
  pasa siempre por `api-general` (ver reglas cross-repo de la constitution).
