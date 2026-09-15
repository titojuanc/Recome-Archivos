---

description: "Task list for 003-webserver-archivos implementation"
---

# Tasks: Webserver de Acceso Restringido a Reportes

**Input**: Design documents from `/specs/003-webserver-archivos/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Esta feature usa **TDD estricto** por mandato de la constitution (Principio
VII, NON-NEGOTIABLE). Todas las tareas de test se ejecutan y deben **FALLAR** antes de
escribir la implementación correspondiente (Red-Green-Refactor).

**Organization**: Tareas agrupadas por user story (US1, US2, US3), precedidas por Setup
y Foundational. Esta feature agrega un microservicio de autorización
(`src/webserver/auth_service/`), una nueva tabla (`ReporteAutorizacion`), una extensión
de `001-worker-reportes` (`service.py`), y configuración de infraestructura Nginx
(`infra/nginx/nginx.conf`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin dependencias)
- **[Story]**: A qué user story pertenece (US1, US2, US3)

## Path Conventions

Extensión del proyecto worker existente (ver `plan.md`):
- Código: `src/webserver/auth_service/`, `src/models/autorizacion.py`
- Infraestructura: `infra/nginx/nginx.conf`
- Tests: `tests/unit/`, `tests/contract/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialización del microservicio de autorización y su entorno de test

- [ ] T001 Crear estructura `src/webserver/auth_service/{__init__.py, main.py,
      jwt_validator.py, autorizacion_repository.py, config.py}` y
      `src/webserver/__init__.py`, según `plan.md`
- [ ] T002 Agregar dependencias `fastapi`, `uvicorn`, `PyJWT`, `httpx` (para tests) al
      `pyproject.toml` (extiende el de `001-worker-reportes`/`002-minio-storage`)
- [ ] T003 [P] Agregar servicios `auth-service-test` (build local, expone puerto interno
      del microservicio FastAPI) y `nginx-test` (imagen `nginx`, monta
      `infra/nginx/nginx.conf`, expone puerto de test) a `docker-compose.test.yml`
- [ ] T004 [P] Crear `infra/nginx/nginx.conf` base: `location /reportes/{solicitud_id}`
      con `auth_request /auth`, `location = /auth` (proxy interno al
      `auth-service-test`), y `location` interno para `X-Accel-Redirect` hacia el bucket
      de MinIO (`002-minio-storage`)
- [ ] T005 [P] Documentar variables de entorno nuevas (`JWT_SECRET`,
      `AUTH_DATABASE_URL` si difiere de `DATABASE_URL`) en
      `src/webserver/auth_service/config.py`

**Checkpoint**: Entorno de test con Nginx + auth-service disponible para Foundational y
las user stories

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelo de datos y validación de JWT, requeridos por todas las user stories.

**⚠️ CRITICAL**: Ninguna user story puede empezar hasta completar esta fase.

### Tests foundational (escribir PRIMERO, deben FALLAR)

- [ ] T006 [P] Unit test: `jwt_validator.validar_jwt(token)` acepta un JWT válido
      (firma correcta, no expirado) y devuelve el claim `sub`; rechaza (lanza excepción)
      JWT con firma inválida, expirado, o mal formado, en
      `tests/unit/test_jwt_validator.py`
- [ ] T007 [P] Unit test: `autorizacion_repository.obtener_autorizacion(session,
      solicitud_id)` devuelve el registro `ReporteAutorizacion` si existe, o `None` si no,
      en `tests/unit/test_autorizacion_repository.py`

### Implementación foundational (solo después de que T006-T007 fallen)

- [ ] T008 [P] Crear modelo SQLAlchemy `ReporteAutorizacion` en
      `src/models/autorizacion.py` (campos: `solicitud_id` PK, `anuncio_id`,
      `usuario_solicitante`, `bucket`, `key`, `creado_en`), según `data-model.md`
- [ ] T009 [P] Implementar `jwt_validator.py` en
      `src/webserver/auth_service/jwt_validator.py`: función `validar_jwt(token) ->
      str` (devuelve `sub`) usando `PyJWT` con `HS256` y `JWT_SECRET` — satisface T006
- [ ] T010 [P] Implementar `autorizacion_repository.py` en
      `src/webserver/auth_service/autorizacion_repository.py`:
      `obtener_autorizacion(session, solicitud_id) -> ReporteAutorizacion | None` —
      satisface T007 (depende de T008)

**Checkpoint**: Validación de JWT y consulta de autorización listas — las user stories
pueden empezar

---

## Phase 3: User Story 1 - Descargar un reporte propio con acceso autorizado (Priority: P1) 🎯 MVP

**Goal**: Un usuario autorizado con JWT válido puede descargar su reporte; Nginx sirve el
contenido desde MinIO vía `X-Accel-Redirect` sin copiarlo a disco.

**Independent Test**: Insertar un `ReporteAutorizacion` de prueba y un objeto real en
MinIO de test, generar un JWT válido para ese usuario, solicitar
`GET /reportes/{solicitud_id}` y verificar `200` con el contenido correcto.

### Tests for User Story 1 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T011 [P] [US1] Contract test: el endpoint `GET /auth` del microservicio, con JWT
      válido y `X-Solicitud-Id` de un reporte autorizado para ese usuario, responde `200`
      con headers `X-Bucket`/`X-Object-Key`, validado contra
      `specs/003-webserver-archivos/contracts/auth_endpoint.schema.json`, en
      `tests/contract/test_auth_endpoint_contract.py`
- [ ] T012 [US1] Integration test (Nginx + auth-service + MinIO + Postgres reales):
      `GET /reportes/{solicitud_id}` con JWT válido del usuario autorizado devuelve `200`
      y el contenido es idéntico byte a byte al objeto persistido en MinIO (Acceptance
      Scenario 1), en `tests/integration/test_webserver_descarga.py`
- [ ] T013 [US1] Integration test: repetir la misma solicitud del reporte tras un tiempo
      razonable (nueva conexión) sigue devolviendo `200` mientras el objeto exista en
      MinIO (Acceptance Scenario 2), en `tests/integration/test_webserver_descarga.py`
- [ ] T014 [US1] Unit test: `service.procesar_solicitud()` de `001-worker-reportes`,
      cuando recibe un `autorizacion_repository` y la subida a MinIO es exitosa, registra
      un `ReporteAutorizacion` con `solicitud_id`/`usuario_solicitante`/`bucket`/`key`
      correctos, en `tests/unit/test_service.py`

### Implementation for User Story 1 (solo después de que T011-T014 fallen)

- [ ] T015 [US1] Implementar el endpoint `GET /auth` en
      `src/webserver/auth_service/main.py` (FastAPI): valida JWT (T009), consulta
      autorización (T010), responde `200` + headers `X-Bucket`/`X-Object-Key` si
      coincide `sub` con `usuario_solicitante` — satisface T011 (depende de T009, T010)
- [ ] T016 [US1] Completar `infra/nginx/nginx.conf`: `auth_request_set` para capturar
      `X-Bucket`/`X-Object-Key` de la respuesta de `/auth`, y usarlos para construir el
      `X-Accel-Redirect` hacia el `location` interno que proxea a MinIO — satisface T012
      (depende de T004, T015)
- [ ] T017 [US1] Integrar `autorizacion_repository` en
      `src/worker/reportes/service.py` (`procesar_solicitud()`): tras
      `persistencia.subir_reporte()` exitoso, si se provee `autorizacion_repository`,
      registrar el `ReporteAutorizacion` correspondiente — satisface T014 (depende de
      T008; modifica un archivo de la feature `001-worker-reportes`, coordinar con su
      estado)

**Checkpoint**: User Story 1 debe ser completamente funcional y testeable de forma
independiente — MVP de esta feature alcanzado

---

## Phase 4: User Story 2 - Rechazar acceso no autorizado (Priority: P1)

**Goal**: Solicitudes sin JWT, con JWT inválido/expirado, o de un usuario distinto al
autorizado, son rechazadas sin exponer contenido ni metadata del archivo.

**Independent Test**: Solicitar el mismo reporte de US1 sin credenciales, con credenciales
inválidas, y con credenciales de un usuario distinto, verificando `401`/`403` según
corresponda y que el contenido nunca se transmite.

### Tests for User Story 2 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T018 [P] [US2] Contract test: `GET /auth` sin header `Authorization` responde
      `401`, en `tests/contract/test_auth_endpoint_contract.py`
- [ ] T019 [P] [US2] Contract test: `GET /auth` con JWT de firma inválida o expirado
      responde `401`, en `tests/contract/test_auth_endpoint_contract.py`
- [ ] T020 [P] [US2] Contract test: `GET /auth` con JWT válido pero `sub` distinto al
      `usuario_solicitante` del `ReporteAutorizacion` responde `403`, en
      `tests/contract/test_auth_endpoint_contract.py`
- [ ] T021 [US2] Integration test (Nginx + auth-service reales): `GET
      /reportes/{solicitud_id}` sin credenciales devuelve `401` y no transmite contenido
      (Acceptance Scenario 2), en `tests/integration/test_webserver_descarga.py`
- [ ] T022 [US2] Integration test: `GET /reportes/{solicitud_id}` con JWT de un usuario
      distinto al autorizado devuelve `403` y no transmite contenido (Acceptance
      Scenario 1), en `tests/integration/test_webserver_descarga.py`
- [ ] T023 [US2] Integration test: `GET /reportes/{solicitud_id}` con JWT expirado
      devuelve `401` (Acceptance Scenario 3), en
      `tests/integration/test_webserver_descarga.py`

### Implementation for User Story 2 (solo después de que T018-T023 fallen)

- [ ] T024 [US2] Ajustar el endpoint `/auth` (`src/webserver/auth_service/main.py`) para
      distinguir explícitamente `401` (JWT ausente/inválido/expirado) de `403` (usuario no
      coincide) — satisface T018-T020, T023 (depende de T015; en la mayoría de los casos
      ya cumple por diseño de T009/T015, esta tarea es de verificación explícita y ajuste
      si hiciera falta)
- [ ] T025 [US2] Verificar que `infra/nginx/nginx.conf` propaga fielmente el código de
      estado del subrequest `/auth` (`401`/`403`) hacia el cliente, sin sustituirlo por un
      genérico `500`/`403` — satisface T021, T022 (depende de T016)

**Checkpoint**: User Stories 1 y 2 funcionan correctamente en conjunto y de forma
independiente — control de acceso completo (FR-001 a FR-003, FR-005, FR-006)

---

## Phase 5: User Story 3 - Manejar reportes inexistentes o ya eliminados (Priority: P2)

**Goal**: Solicitudes sobre un `solicitud_id` sin `ReporteAutorizacion` (inexistente,
mal formado, o cuyo objeto ya fue eliminado por retención) responden `404` de forma
consistente, sin filtrar detalles internos de MinIO.

**Independent Test**: Solicitar un `solicitud_id` inexistente (con JWT válido de
cualquier usuario) y verificar `404`; simular un objeto eliminado de MinIO (autorización
existe pero el objeto ya no) y verificar que igualmente se informa como no disponible sin
exponer el error nativo de MinIO.

### Tests for User Story 3 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T026 [P] [US3] Contract test: `GET /auth` con `X-Solicitud-Id` que no tiene
      `ReporteAutorizacion` responde `404`, en
      `tests/contract/test_auth_endpoint_contract.py`
- [ ] T027 [US3] Integration test: `GET /reportes/{solicitud_id}` con un `solicitud_id`
      inexistente o mal formado devuelve `404` sin filtrar información interna de MinIO
      (Acceptance Scenario 2), en `tests/integration/test_webserver_descarga.py`
- [ ] T028 [US3] Integration test: `GET /reportes/{solicitud_id}` autorizado, pero cuyo
      objeto ya fue eliminado de MinIO (simulado eliminándolo tras crear la
      autorización), devuelve una respuesta de "ya no disponible" sin exponer el error
      nativo de MinIO (Acceptance Scenario 1), en
      `tests/integration/test_webserver_descarga.py`

### Implementation for User Story 3 (solo después de que T026-T028 fallen)

- [ ] T029 [US3] Confirmar/ajustar el endpoint `/auth` para responder `404` cuando no
      exista `ReporteAutorizacion` — satisface T026 (depende de T010, T015; en la
      mayoría de los casos ya cumple por diseño, esta tarea es de verificación explícita)
- [ ] T030 [US3] Ajustar el `location` interno de `X-Accel-Redirect` en
      `infra/nginx/nginx.conf` para traducir un error de MinIO al intentar leer un objeto
      inexistente (ej. `404`/`403` nativo de MinIO) en una respuesta genérica del
      webserver, sin exponer el body/headers originales de MinIO — satisface T027, T028
      (depende de T016)

**Checkpoint**: Las tres user stories funcionan de forma independiente y en conjunto;
FR-001 a FR-009 cubiertos íntegramente

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Mejoras que afectan a todas las user stories, cierre de la feature

- [ ] T031 [P] Integration test: disparar múltiples solicitudes concurrentes de
      descarga del mismo reporte por el mismo usuario autorizado (`ThreadPoolExecutor` o
      similar) y verificar que todas responden `200` sin errores de interferencia
      (FR-010, SC-003), en `tests/integration/test_webserver_descarga.py`
- [ ] T032 [P] Integration test: simular que MinIO no responde momentáneamente durante
      un `X-Accel-Redirect` ya autorizado, y verificar que el webserver informa un error
      transitorio (5xx) sin exponer contenido ni "cachear" la autorización como entregada
      (Edge Case de disponibilidad, FR-008), en
      `tests/integration/test_webserver_descarga.py`
- [ ] T033 [P] Verificar que `JWT_SECRET` y la configuración de acceso del webserver
      solo se referencian dentro de `src/webserver/` y su configuración de despliegue,
      sin fugas hacia otros módulos (FR-009)
- [ ] T034 [P] Actualizar `quickstart.md` si difiere de la implementación final (nombres
      de funciones, variables de entorno, puertos)
- [ ] T035 Ejecutar manualmente los pasos de `quickstart.md` de punta a punta (200,
      401, 403, 404)
- [ ] T036 Ejecutar suite completa (`pytest tests/unit tests/contract
      tests/integration`) y confirmar 100% verde antes de cerrar la feature

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias — arranca de inmediato
- **Foundational (Phase 2)**: depende de Setup — BLOQUEA todas las user stories
- **User Stories (Phase 3-5)**: dependen de Foundational
  - US1 (P1) puede arrancar sola apenas termina Foundational
  - US2 (P1) depende del endpoint `/auth` de US1 (T015) para verificar/ajustar sus
    respuestas `401`/`403`; es independientemente testeable una vez integrada
  - US3 (P2) depende igualmente del endpoint `/auth` de US1 (T015) para verificar/ajustar
    su respuesta `404`
- **Polish (Phase 6)**: depende de que US1-US3 estén completas

### Dentro de cada User Story

- Tests se escriben y deben FALLAR antes de cualquier implementación (Principio VII)
- `jwt_validator`/`autorizacion_repository` (Foundational) antes que el endpoint `/auth`
  (US1)
- El endpoint `/auth` completo (US1) antes de verificar sus respuestas de rechazo (US2,
  US3)
- La integración con `service.py` de la feature `001` (T017) es el punto de conexión
  cross-feature; requiere que `001-worker-reportes` esté implementada para poder
  integrarse de punta a punta

### Oportunidades de Paralelismo

- T003-T005 (Setup) en paralelo
- T006-T007 (tests foundational) en paralelo; T008-T010 (implementación) en paralelo
  tras fallar sus tests (T008 primero, ya que T010 depende de él)
- T018-T020 (contract tests de US2) en paralelo entre sí
- T026 (contract test de US3) en paralelo con la preparación de T027-T028
- T031-T034 (Polish) en paralelo entre sí

---

## Implementation Strategy

### MVP First (User Story 1 solamente)

1. Completar Phase 1 (Setup) y Phase 2 (Foundational)
2. Completar Phase 3 (US1) siguiendo TDD: T011-T014 en rojo → T015-T017 hasta verde
3. **DETENER y VALIDAR**: correr `quickstart.md` pasos 1-4 de forma independiente
4. Demo/checkpoint: un usuario autorizado descarga su reporte real desde MinIO a través
   de Nginx

### Entrega Incremental

1. Setup + Foundational → base lista
2. US1 → validar independientemente → MVP de la feature (descarga autorizada funcional)
3. US2 → validar independientemente (rechazo de accesos no autorizados) → demo
4. US3 → validar independientemente (manejo de reportes inexistentes/eliminados) → demo
5. Polish → cierre de la feature

---

## Notes

- [P] = archivos distintos, sin dependencias entre sí
- [Story] mapea cada tarea a su user story para trazabilidad
- **TDD obligatorio** (Principio VII, NON-NEGOTIABLE): en Foundational, US1, US2 y US3,
  las tareas de test preceden a las de implementación y deben fallar antes de escribir el
  código que las satisface
- La tarea T017 modifica un archivo de la feature `001-worker-reportes`
  (`src/worker/reportes/service.py`); coordinar el orden de implementación entre ambas
  features si se desarrollan en paralelo por personas distintas
- Commitear después de cada tarea o grupo lógico (test rojo → implementación → test
  verde)
- Detenerse en cada checkpoint para validar la user story de forma independiente antes
  de continuar con la siguiente
