---

description: "Task list for 001-worker-reportes implementation"
---

# Tasks: Worker de Generación de Reportes (Excel) + Modelo SQL de Anuncios

**Input**: Design documents from `/specs/001-worker-reportes/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Esta feature usa **TDD estricto** por mandato de la constitution (Principio
VII, NON-NEGOTIABLE). Todas las tareas de test se ejecutan y deben **FALLAR** antes de
escribir la implementación correspondiente (ciclo Red-Green-Refactor). Ninguna tarea de
implementación se marca completa sin que su(s) test(s) asociados hayan pasado de rojo a
verde.

**Organization**: Tareas agrupadas por user story (US1, US2, US3) para permitir
implementación y prueba independientes, precedidas por Setup y Foundational.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin dependencias)
- **[Story]**: A qué user story pertenece (US1, US2, US3)
- Rutas de archivo exactas incluidas en cada descripción

## Path Conventions

Proyecto único (worker standalone), según `plan.md`:
- Código: `src/worker/`, `src/models/`
- Tests: `tests/unit/`, `tests/contract/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialización del proyecto y estructura básica

- [ ] T001 Crear estructura de directorios `src/worker/{events,reportes,idempotencia}`,
      `src/models/`, `tests/{unit,contract,integration}` según `plan.md`
- [ ] T002 Inicializar proyecto Python 3.12 con `pyproject.toml`/`requirements.txt`:
      `pika`, `openpyxl`, `pydantic`, `SQLAlchemy` + `psycopg[binary]` (o `asyncpg` si se
      opta por async), `pytest`, `pytest-asyncio`, `testcontainers`
- [ ] T003 [P] Configurar linting/formatting (`ruff` + `black` o equivalente) y hook de
      pre-commit
- [ ] T004 [P] Configurar `docker-compose.test.yml` con RabbitMQ y PostgreSQL para tests
      de integración, siguiendo `quickstart.md`

**Checkpoint**: Estructura y tooling listos para empezar Foundational

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infraestructura núcleo que TODAS las user stories necesitan antes de poder
implementarse. Incluye los tests de contrato base (fuente de verdad = `contracts/`),
que deben escribirse y fallar antes de crear los modelos que los satisfacen.

**⚠️ CRITICAL**: Ninguna user story puede empezar hasta completar esta fase.

### Tests de contrato (escribir PRIMERO, deben FALLAR)

- [ ] T005 [P] Contract test: `SolicitudDeReporte` valida correctamente contra
      `specs/001-worker-reportes/contracts/reporte.generar.schema.json` (campos
      requeridos, tipos, `additionalProperties: false`) en
      `tests/contract/test_reporte_generar_schema.py`
- [ ] T006 [P] Contract test: `ReporteGenerado` valida correctamente contra
      `specs/001-worker-reportes/contracts/reporte.listo.schema.json` en
      `tests/contract/test_reporte_listo_schema.py`

### Implementación foundational (solo después de que T005-T006 fallen)

- [ ] T007 [P] Modelo `pydantic` `SolicitudDeReporte` (con `extra="forbid"`) en
      `src/worker/events/schemas.py`, satisfaciendo T005
- [ ] T008 [P] Modelo `pydantic` `ReporteGenerado` en `src/worker/events/schemas.py`,
      satisfaciendo T006
- [ ] T009 [P] Modelo `Anuncio` (mapeo de la tabla compartida `anuncio`) en
      `src/models/anuncio.py`, según `data-model.md`
- [ ] T010 [P] Modelo `RegistroDeIdempotencia` (tabla propia, no compartida) en
      `src/models/idempotencia.py`, según `data-model.md`
- [ ] T011 Configuración de entorno (`src/worker/config.py`): `RABBITMQ_URL`,
      `DATABASE_URL`, nombres de colas/exchanges (`reporte.generar`, `reporte.listo`,
      dead-letter), pool de conexiones SQL, límite de concurrencia (para FR-012)
- [ ] T012 Infraestructura de logging estructurado y manejo de errores base en
      `src/worker/main.py` (placeholder de entry point, sin lógica de negocio aún)

**Checkpoint**: Modelos y validación de contratos listos — las user stories pueden
empezar en paralelo

---

## Phase 3: User Story 1 - Generar un reporte Excel a partir de un pedido válido (Priority: P1) 🎯 MVP

**Goal**: Consumir `reporte.generar` válido, consultar `anuncio`, generar el Excel de dos
hojas (impresiones/clicks, con "N/D" en campos corruptos) y publicar `reporte.listo`.

**Independent Test**: Publicar un evento `reporte.generar` válido contra una cola de
test y verificar que se genera el Excel esperado y se publica `reporte.listo` correcto,
sin depender de MinIO ni webserver (mockeando la persistencia final del archivo).

### Tests for User Story 1 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T013 [P] [US1] Unit test: `repository.obtener_eventos_anuncio()` filtra por
      `anuncio_id` + rango de fechas, e incluye siempre registros con `timestamp` nulo
      (Clarification #6) en `tests/unit/test_repository.py`
- [ ] T014 [P] [US1] Unit test: `excel_builder.construir_reporte()` genera un workbook
      con hojas `Impresiones` y `Clicks`, marca campos nulos/corruptos como `"N/D"`, y
      genera hojas con solo encabezados cuando no hay datos, en
      `tests/unit/test_excel_builder.py`
- [ ] T015 [P] [US1] Unit test: `service.procesar_solicitud()` orquesta
      validar→consultar→generar→publicar, y no publica `reporte.listo` si algún paso
      previo falla, en `tests/unit/test_service.py`
- [ ] T016 [US1] Integration test: flujo end-to-end contra RabbitMQ + PostgreSQL reales
      (docker-compose) — publicar `reporte.generar` válido con datos de impresiones y
      clicks, verificar Excel generado (Acceptance Scenario 1) y evento `reporte.listo`
      con `estado: "generado"`, en `tests/integration/test_flujo_end_to_end.py`
- [ ] T017 [US1] Integration test: mismo flujo pero con `anuncio_id` sin datos en el
      rango — verificar Excel con hojas vacías (solo encabezados) y `estado: "vacio"`
      (Acceptance Scenario 2), en `tests/integration/test_flujo_end_to_end.py`
- [ ] T018 [US1] Integration test: verificar que el mensaje se hace `ack` solo tras
      éxito completo y no se reprocesa (Acceptance Scenario 3), en
      `tests/integration/test_worker_rabbitmq.py`

### Implementation for User Story 1 (solo después de que T013-T018 fallen)

- [ ] T019 [P] [US1] Implementar `repository.py` en `src/worker/reportes/repository.py`:
      consulta a `anuncio` con cursor server-side/paginado por lotes (keyset pagination),
      incluyendo el `OR timestamp IS NULL` de `data-model.md` — satisface T013
- [ ] T020 [P] [US1] Implementar `excel_builder.py` en
      `src/worker/reportes/excel_builder.py`: `openpyxl.Workbook(write_only=True)` con
      dos hojas, escritura incremental fila por fila, marcado "N/D" — satisface T014
- [ ] T021 [US1] Implementar `service.py` en `src/worker/reportes/service.py`:
      orquestación validar→consultar→generar→publicar, usando T019 y T020 — satisface
      T015 (depende de T019, T020)
- [ ] T022 [US1] Implementar `consumer.py` en `src/worker/events/consumer.py`: consumo de
      `reporte.generar`, invocación de `service.procesar_solicitud()`, `ack` solo tras
      éxito — satisface T016-T018 (depende de T021)
- [ ] T023 [US1] Implementar `publisher.py` en `src/worker/events/publisher.py`:
      publicación de `reporte.listo` con el payload validado — satisface T016-T017
      (depende de T008)
- [ ] T024 [US1] Conectar `main.py` (`src/worker/main.py`) para levantar la conexión a
      RabbitMQ, registrar el consumer, y correr el loop de consumo

**Checkpoint**: User Story 1 debe ser completamente funcional y testeable de forma
independiente — MVP alcanzado

---

## Phase 4: User Story 2 - Rechazar eventos inválidos o mal formados (Priority: P2)

**Goal**: Rechazar (nack/dead-letter) eventos que no cumplen el schema o referencian un
`anuncio_id` inexistente, sin generar archivos ni publicar `reporte.listo`.

**Independent Test**: Publicar eventos deliberadamente inválidos (sin `anuncio_id`, rango
de fechas invertido, `anuncio_id` inexistente) y verificar rechazo sin efectos
secundarios.

### Tests for User Story 2 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T025 [P] [US2] Unit test: validación de `SolicitudDeReporte` rechaza payload sin
      `anuncio_id` y payload con `fecha_desde > fecha_hasta` en
      `tests/unit/test_service.py`
- [ ] T026 [P] [US2] Unit test: `service.procesar_solicitud()` rechaza (levanta
      excepción específica) cuando `anuncio_id` no existe en `anuncio`, distinguiéndolo
      explícitamente del caso "anuncio existe sin datos" (US1 Scenario 2), en
      `tests/unit/test_service.py`
- [ ] T027 [US2] Integration test: publicar evento sin `anuncio_id` → verificar `nack` +
      enrutamiento a dead-letter, sin archivo ni `reporte.listo` (Acceptance Scenario 1),
      en `tests/integration/test_worker_rabbitmq.py`
- [ ] T028 [US2] Integration test: publicar evento con rango de fechas inválido →
      mismo rechazo (Acceptance Scenario 2), en `tests/integration/test_worker_rabbitmq.py`
- [ ] T029 [US2] Integration test: publicar evento con `anuncio_id` inexistente →
      rechazo, no genera reporte vacío disfrazado de válido (Acceptance Scenario 3), en
      `tests/integration/test_worker_rabbitmq.py`

### Implementation for User Story 2 (solo después de que T025-T029 fallen)

- [ ] T030 [US2] Agregar validación de rango (`fecha_desde <= fecha_hasta`) al modelo
      `SolicitudDeReporte` en `src/worker/events/schemas.py` (validator de `pydantic`) —
      satisface T025
- [ ] T031 [US2] Agregar verificación de existencia de `anuncio_id` en
      `src/worker/reportes/service.py`, levantando una excepción de dominio específica
      (`AnuncioInexistente`) — satisface T026 (depende de T019)
- [ ] T032 [US2] Implementar manejo de rechazo (`nack` + publicación a dead-letter
      exchange) en `src/worker/events/consumer.py` ante fallos de validación o
      `AnuncioInexistente` — satisface T027-T029 (depende de T022, T030, T031)

**Checkpoint**: User Stories 1 y 2 funcionan correctamente en conjunto y de forma
independiente

---

## Phase 5: User Story 3 - Recuperación ante fallos transitorios (Priority: P3)

**Goal**: Ante fallos transitorios de conexión (DB/RabbitMQ), no perder el evento ni
duplicar el reporte al reintentar.

**Independent Test**: Simular una caída de conexión a la DB durante el procesamiento y
verificar que el mensaje no se pierde (no ack), y que un reintento posterior genera un
único reporte.

### Tests for User Story 3 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T033 [P] [US3] Unit test: `idempotencia/store.py` marca una solicitud como
      `en_proceso` al iniciar, `completado` al terminar exitosamente, y permite
      reintentar si quedó en `en_proceso`/`fallido` tras una caída, en
      `tests/unit/test_idempotencia.py`
- [ ] T034 [US3] Integration test: simular falla de conexión a la DB a mitad de una
      consulta (mock/fault injection) → verificar que el mensaje no se hace `ack`
      (Acceptance Scenario 1), en `tests/integration/test_worker_db_anuncio.py`
- [ ] T035 [US3] Integration test: reintentar un evento con `solicitud_id` ya marcado
      `completado` → verificar que no se genera un segundo reporte ni un segundo
      `reporte.listo` (Acceptance Scenario 2, SC-003), en
      `tests/integration/test_flujo_end_to_end.py`

### Implementation for User Story 3 (solo después de que T033-T035 fallen)

- [ ] T036 [US3] Implementar `store.py` en `src/worker/idempotencia/store.py`: consulta y
      actualización de `RegistroDeIdempotencia` (estados `en_proceso`/`completado`/
      `fallido`) — satisface T033 (depende de T010)
- [ ] T037 [US3] Integrar `store.py` en `service.procesar_solicitud()`
      (`src/worker/reportes/service.py`): chequeo de idempotencia antes de procesar,
      marcado de estado en cada etapa, no-ack ante excepción transitoria — satisface
      T034-T035 (depende de T021, T036)
- [ ] T038 [US3] Implementar concurrencia interna acotada (FR-012): pool de tareas
      (async/threads) con límite configurable en `src/worker/events/consumer.py`,
      correlacionado con `prefetch_count` de RabbitMQ (depende de T022, T011)

**Checkpoint**: Las tres user stories funcionan de forma independiente y en conjunto

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Mejoras que afectan a todas las user stories, cierre de la feature

- [ ] T039 [P] Test de volumen/performance: generar reporte con ~100.000 registros y
      verificar que se completa en menos de 30s (SC-001), en
      `tests/integration/test_flujo_end_to_end.py`
- [ ] T040 [P] Test de concurrencia: publicar 50 solicitudes simultáneas y verificar que
      no hay pérdida de eventos ni caída del proceso (SC-004), en
      `tests/integration/test_worker_rabbitmq.py`
- [ ] T041 [P] Documentar variables de entorno y operación del worker en
      `specs/001-worker-reportes/quickstart.md` (ajustar si difiere de la implementación
      final)
- [ ] T042 Revisar y ejecutar manualmente los pasos de `quickstart.md` de punta a punta
- [ ] T043 [P] Logging estructurado final (niveles, correlación por `solicitud_id`) en
      `src/worker/reportes/service.py` y `src/worker/events/consumer.py`
- [ ] T044 Ejecutar suite completa (`pytest tests/unit tests/contract tests/integration`)
      y confirmar 100% verde antes de cerrar la feature

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias — arranca de inmediato
- **Foundational (Phase 2)**: depende de Setup — BLOQUEA todas las user stories
- **User Stories (Phase 3-5)**: dependen de Foundational
  - US1 (P1) puede arrancar sola apenas termina Foundational
  - US2 (P2) depende de que existan `repository.py`/`service.py` de US1 (T019, T021) para
    agregar sus validaciones, pero es independientemente testeable una vez integrada
  - US3 (P3) depende de `service.py` de US1 (T021) y de `RegistroDeIdempotencia` (T010)
    para integrarse, y es independientemente testeable una vez integrada
- **Polish (Phase 6)**: depende de que US1-US3 estén completas

### Dentro de cada User Story

- Tests se escriben y deben FALLAR antes de cualquier implementación (TDD estricto,
  Principio VII de la constitution)
- Modelos/repositorios antes de servicios
- Servicios antes de consumer/publisher
- Implementación core antes de integración con fases anteriores

### Oportunidades de Paralelismo

- Todas las tareas [P] de Setup pueden correr en paralelo
- T005-T006 (contract tests) en paralelo; T007-T010 (modelos) en paralelo entre sí tras
  fallar sus tests
- T013-T015 (unit tests de US1) en paralelo; T019-T020 (repository/excel_builder) en
  paralelo tras fallar sus tests
- T025-T026 (unit tests de US2) en paralelo
- T033 (unit test de US3) puede correr en paralelo con tareas de otras stories si no
  comparten archivo

---

## Implementation Strategy

### MVP First (User Story 1 solamente)

1. Completar Phase 1 (Setup) y Phase 2 (Foundational)
2. Completar Phase 3 (US1) siguiendo TDD: T013-T018 en rojo → T019-T024 hasta verde
3. **DETENER y VALIDAR**: correr `quickstart.md` pasos 1-6 de forma independiente
4. Demo/checkpoint del MVP

### Entrega Incremental

1. Setup + Foundational → base lista
2. US1 → validar independientemente → MVP demostrable
3. US2 → validar independientemente (incluyendo que no rompe US1) → demo
4. US3 → validar independientemente (incluyendo que no rompe US1/US2) → demo
5. Polish → cierre de la feature

---

## Notes

- [P] = archivos distintos, sin dependencias entre sí
- [Story] mapea cada tarea a su user story para trazabilidad
- **TDD obligatorio**: en cada fase, las tareas de test preceden a las de implementación
  y deben fallar antes de escribir el código que las satisface (Red-Green-Refactor);
  no se marca una tarea de test como completada hasta confirmar que falla, ni una tarea
  de implementación como completada hasta que su test correspondiente pasa a verde
- Commitear después de cada tarea o grupo lógico (test rojo → implementación → test
  verde, como una unidad de commit cuando sea posible)
- Detenerse en cada checkpoint para validar la user story de forma independiente antes
  de continuar con la siguiente
