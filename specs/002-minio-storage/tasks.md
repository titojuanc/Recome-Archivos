---

description: "Task list for 002-minio-storage implementation"
---

# Tasks: Persistencia de Reportes Generados en MinIO

**Input**: Design documents from `/specs/002-minio-storage/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Esta feature usa **TDD estricto** por mandato de la constitution (Principio
VII, NON-NEGOTIABLE). Todas las tareas de test se ejecutan y deben **FALLAR** antes de
escribir la implementación correspondiente (Red-Green-Refactor). La retención (US3) es
una excepción parcial: al resolverse vía configuración de infraestructura (lifecycle
rules nativas de MinIO, Clarification #2), su "test" es un test de integración que
verifica el comportamiento de esa configuración, no hay lógica propia que preceda con
un unit test rojo.

**Organization**: Tareas agrupadas por user story (US1, US2, US3), precedidas por Setup
y Foundational. Esta feature se integra como submódulo (`src/worker/storage/`) del mismo
proyecto worker de `001-worker-reportes`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin dependencias)
- **[Story]**: A qué user story pertenece (US1, US2, US3)

## Path Conventions

Extensión del proyecto worker existente (ver `plan.md`):
- Código: `src/worker/storage/`
- Infraestructura: `infra/minio/`
- Tests: `tests/unit/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialización del submódulo de storage y su entorno de test

- [ ] T001 Crear estructura `src/worker/storage/{__init__.py, minio_client.py,
      key_builder.py, persistencia.py}` e `infra/minio/` según `plan.md`
- [ ] T002 Agregar dependencia `minio` (SDK oficial) al `requirements.txt`/
      `pyproject.toml` del worker (extiende el de `001-worker-reportes`)
- [ ] T003 [P] Agregar servicio MinIO a `docker-compose.test.yml` (imagen `minio/minio`,
      credenciales de test, puerto 9000/9001), según `quickstart.md`
- [ ] T004 [P] Documentar variables de entorno nuevas (`MINIO_ENDPOINT`,
      `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE`) en
      `src/worker/config.py` (extiende la config existente de `001`)

**Checkpoint**: Entorno de test con MinIO disponible para Foundational y las user stories

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infraestructura núcleo que TODAS las user stories necesitan: cliente MinIO
configurado y lógica de derivación de key (pura, sin I/O), ambas requeridas antes de
poder persistir nada.

**⚠️ CRITICAL**: Ninguna user story puede empezar hasta completar esta fase.

### Tests foundational (escribir PRIMERO, deben FALLAR)

- [ ] T005 [P] Unit test: `key_builder.construir_key(anuncio_id, solicitud_id)` produce
      siempre `reportes/{anuncio_id}/{solicitud_id}.xlsx`, es determinística (mismo input
      → mismo output) y estable ante inputs con caracteres especiales en `anuncio_id`, en
      `tests/unit/test_key_builder.py`
- [ ] T006 [P] Integration test: `minio_client` se conecta exitosamente al MinIO de test
      (docker-compose) y puede verificar/crear el bucket configurado, en
      `tests/integration/test_minio_persistencia.py` (test de conexión, primer caso)

### Implementación foundational (solo después de que T005-T006 fallen)

- [ ] T007 [P] Implementar `key_builder.py` en `src/worker/storage/key_builder.py`:
      función pura `construir_key(anuncio_id, solicitud_id) -> str` — satisface T005
- [ ] T008 [P] Implementar `minio_client.py` en `src/worker/storage/minio_client.py`:
      wrapper del SDK `minio` (conexión desde config, verificación/creación de bucket al
      iniciar) — satisface T006 (depende de T004)

**Checkpoint**: Cliente MinIO y derivación de keys listos — las user stories pueden
empezar

---

## Phase 3: User Story 1 - Persistir un reporte generado de forma recuperable (Priority: P1) 🎯 MVP

**Goal**: Subir el Excel generado por `001-worker-reportes` a MinIO en una ubicación
determinística, verificar integridad de forma bloqueante, y producir la
`ReferenciaDeArchivo` que se incluye en `reporte.listo`.

**Independent Test**: Tomar un archivo Excel ya generado (mock de la feature `001`),
persistirlo, y verificar que queda en la ubicación esperada, es recuperable byte a byte,
y la referencia devuelta es la correcta.

### Tests for User Story 1 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T009 [P] [US1] Unit test: `persistencia.calcular_checksum(archivo)` produce un hash
      consistente y reproducible para el mismo contenido, en
      `tests/unit/test_persistencia_checksum.py`
- [ ] T010 [US1] Integration test (MinIO real): `persistencia.subir_reporte(...)` sube un
      archivo y la key resultante coincide con la esperada por `key_builder`
      (Acceptance Scenario 1), en `tests/integration/test_minio_persistencia.py`
- [ ] T011 [US1] Integration test (MinIO real): el contenido recuperado vía
      `get_object` con la `key` devuelta es idéntico byte a byte al archivo original
      (Acceptance Scenario 2, SC-003), en `tests/integration/test_minio_persistencia.py`
- [ ] T012 [US1] Integration test (MinIO real): tras una subida exitosa,
      `persistencia.subir_reporte(...)` devuelve una `ReferenciaDeArchivo` con
      `bucket`/`key`/`etag` válidos para el evento `reporte.listo` (Acceptance
      Scenario 3), validada además contra
      `specs/002-minio-storage/contracts/referencia_archivo.schema.json`, en
      `tests/integration/test_minio_persistencia.py`
- [ ] T013 [US1] Integration test (MinIO real): si el ETag devuelto no coincide con el
      checksum local (simulado con mock/fault injection), `persistencia.subir_reporte(...)`
      lanza una excepción de fallo de persistencia sin considerar la solicitud completada
      (FR-004, Clarification #4), en `tests/integration/test_minio_persistencia.py`

### Implementation for User Story 1 (solo después de que T009-T013 fallen)

- [ ] T014 [US1] Implementar `calcular_checksum()` en
      `src/worker/storage/persistencia.py` (hash MD5/similar sobre el stream del
      archivo) — satisface T009
- [ ] T015 [US1] Implementar `subir_reporte(anuncio_id, solicitud_id, archivo) ->
      ReferenciaDeArchivo` en `src/worker/storage/persistencia.py`: usa `key_builder`
      (T007) y `minio_client` (T008), sube vía `put_object` con streaming (FR-009),
      calcula checksum antes de subir — satisface T010, T012 (depende de T007, T008,
      T014)
- [ ] T016 [US1] Agregar verificación bloqueante de integridad (comparar `etag` devuelto
      vs. checksum local) en `subir_reporte()`, lanzando excepción de fallo de
      persistencia si no coincide — satisface T011, T013 (depende de T015)
- [ ] T017 [US1] Integrar `persistencia.subir_reporte()` en el flujo del worker de
      `001-worker-reportes` (`src/worker/reportes/service.py`): invocar tras generar el
      Excel exitosamente, e incluir la `ReferenciaDeArchivo` resultante en el payload de
      `reporte.listo` antes de publicarlo (depende de T015, T016; modifica un archivo de
      la feature `001`, coordinar con su estado)

**Checkpoint**: User Story 1 debe ser completamente funcional y testeable de forma
independiente — MVP de esta feature alcanzado

---

## Phase 4: User Story 2 - Evitar sobrescritura o pérdida ante reintentos (Priority: P2)

**Goal**: Garantizar que reintentar la misma solicitud sobrescribe de forma consistente
(sin verificación previa) y que una subida fallida a mitad de camino nunca deja un
objeto parcial visible.

**Independent Test**: Subir el mismo archivo dos veces con el mismo `solicitud_id` y
verificar un único objeto consistente; simular corte de conexión a mitad de subida y
verificar que no queda un objeto parcial accesible.

### Tests for User Story 2 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T018 [P] [US2] Integration test (MinIO real): llamar `subir_reporte()` dos veces
      con el mismo `anuncio_id`/`solicitud_id` (mismo contenido) → verificar que la key
      resultante es idéntica ambas veces y que no se crean objetos adicionales
      (Acceptance Scenario 1, FR-006, Clarification #1), en
      `tests/integration/test_minio_persistencia.py`
- [ ] T019 [US2] Integration test (MinIO real, fault injection): simular corte de
      conexión a mitad de una subida (mock del stream/cliente) → verificar que no queda
      ningún objeto accesible bajo esa key tras el fallo (Acceptance Scenario 2, FR-005),
      en `tests/integration/test_minio_persistencia.py`

### Implementation for User Story 2 (solo después de que T018-T019 fallen)

- [ ] T020 [US2] Confirmar/ajustar `subir_reporte()` para que **no** haga ningún chequeo
      de existencia previa (`stat_object`) antes de subir — satisface T018 (depende de
      T015; en la mayoría de los casos ya cumple por diseño de T015, esta tarea es de
      verificación explícita y ajuste si hiciera falta)
- [ ] T021 [US2] Verificar/ajustar el manejo de excepciones de `subir_reporte()` para que
      ante un corte de conexión durante `put_object`, la excepción se propague sin
      intentos de "limpiar" manualmente un objeto parcial (confiando en la atomicidad
      nativa del SDK) — satisface T019 (depende de T015, T016)

**Checkpoint**: User Stories 1 y 2 funcionan correctamente en conjunto y de forma
independiente

---

## Phase 5: User Story 3 - Retención y limpieza de reportes antiguos (Priority: P3)

**Goal**: Configurar una lifecycle rule nativa de MinIO que elimine automáticamente
objetos del prefijo `reportes/` tras el período de retención configurado, sin código
propio de limpieza (Clarification #2).

**Independent Test**: Configurar una lifecycle rule de expiración corta sobre un prefijo
de prueba, subir un objeto, y verificar que se elimina automáticamente tras el período
configurado, mientras un objeto reciente en otro prefijo permanece intacto.

### Tests for User Story 3 (escribir PRIMERO, deben FALLAR) ⚠️

- [ ] T022 [US3] Integration test: configurar (vía `mc ilm` o API equivalente) una
      lifecycle rule de expiración corta (ej. 1 día, o el mínimo soportado por el
      entorno de test) sobre un prefijo de prueba, subir un objeto, y verificar que
      efectivamente se elimina tras el período configurado (Acceptance Scenario 1,
      SC-004), en `tests/integration/test_minio_lifecycle_rules.py`
- [ ] T023 [US3] Integration test: un objeto subido dentro del período de retención
      permanece intacto y accesible tras evaluarse la lifecycle rule (Acceptance
      Scenario 2), en `tests/integration/test_minio_lifecycle_rules.py`

### Implementation for User Story 3 (solo después de que T022-T023 fallen — o se confirme la configuración)

- [ ] T024 [US3] Crear `infra/minio/lifecycle-rules.json` con la definición de la regla
      de expiración sobre el prefijo `reportes/` (`dias_retencion` configurable) —
      satisface T022, T023
- [ ] T025 [US3] Documentar en `specs/002-minio-storage/quickstart.md` (ya redactado) y
      en la documentación operativa del repo el comando `mc ilm rule add` para aplicar
      `lifecycle-rules.json` sobre el bucket de cada entorno (dev/staging/prod) — tarea
      de aplicación de infraestructura, no de código (depende de T024)

**Checkpoint**: Las tres user stories funcionan de forma independiente y en conjunto;
FR-007/FR-008 cubiertos íntegramente por configuración de infraestructura

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Mejoras que afectan a todas las user stories, cierre de la feature

- [ ] T026 [P] Test de volumen: subir un archivo del tamaño máximo esperado (correlacionado
      con SC-001 de `001-worker-reportes`, ~100.000 filas) y verificar que
      `subir_reporte()` no carga el archivo completo en memoria (streaming real, FR-009),
      en `tests/integration/test_minio_persistencia.py`
- [ ] T027 [P] Verificar en CI que `FR-010` se cumple: revisar que las credenciales de
      MinIO (`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`) solo se referencian dentro de
      `src/worker/storage/` y de la configuración del webserver (feature `003`), sin
      fugas hacia otros repos/servicios
- [ ] T028 [P] Actualizar `quickstart.md` si difiere de la implementación final (nombres
      de funciones, variables de entorno)
- [ ] T029 Ejecutar manualmente los pasos de `quickstart.md` de punta a punta, incluyendo
      la configuración real de la lifecycle rule
- [ ] T030 Ejecutar suite completa (`pytest tests/unit tests/integration`) y confirmar
      100% verde antes de cerrar la feature

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias — arranca de inmediato
- **Foundational (Phase 2)**: depende de Setup — BLOQUEA todas las user stories
- **User Stories (Phase 3-5)**: dependen de Foundational
  - US1 (P1) puede arrancar sola apenas termina Foundational
  - US2 (P2) depende de `subir_reporte()` de US1 (T015, T016) para verificar/ajustar su
    comportamiento; es independientemente testeable una vez integrada
  - US3 (P3) es independiente de código (solo configuración de infraestructura); puede
    desarrollarse en paralelo con US1/US2 sin dependencias de implementación, aunque
    conceptualmente se prioriza después por ser la de menor prioridad de negocio
- **Polish (Phase 6)**: depende de que US1-US3 estén completas

### Dentro de cada User Story

- Tests se escriben y deben FALLAR antes de cualquier implementación (Principio VII)
- `key_builder`/`minio_client` (Foundational) antes que `persistencia.py` (US1)
- `persistencia.py` completo (US1) antes de verificar comportamiento de reintento (US2)
- La integración con `service.py` de la feature `001` (T017) es el punto de conexión
  cross-feature; requiere que `001-worker-reportes` esté implementada (al menos su
  `service.py`) para poder integrarse de punta a punta

### Oportunidades de Paralelismo

- T003-T004 (Setup) en paralelo
- T005-T006 (tests foundational) en paralelo; T007-T008 (implementación) en paralelo
  tras fallar sus tests
- T009 (unit test de checksum) en paralelo con la preparación de T010-T013
- T018 puede prepararse en paralelo con T019 (ambos son integration tests de US2)
- T026-T028 (Polish) en paralelo entre sí

---

## Implementation Strategy

### MVP First (User Story 1 solamente)

1. Completar Phase 1 (Setup) y Phase 2 (Foundational)
2. Completar Phase 3 (US1) siguiendo TDD: T009-T013 en rojo → T014-T017 hasta verde
3. **DETENER y VALIDAR**: correr `quickstart.md` pasos 1-5 de forma independiente
4. Demo/checkpoint: un reporte de `001-worker-reportes` ya queda persistido y
   recuperable en MinIO, con referencia incluida en `reporte.listo`

### Entrega Incremental

1. Setup + Foundational → base lista
2. US1 → validar independientemente → MVP de la feature (persistencia funcional)
3. US2 → validar independientemente (reintentos seguros) → demo
4. US3 → configurar y validar independientemente (retención automática) → demo
5. Polish → cierre de la feature

---

## Notes

- [P] = archivos distintos, sin dependencias entre sí
- [Story] mapea cada tarea a su user story para trazabilidad
- **TDD obligatorio** (Principio VII, NON-NEGOTIABLE): en Foundational, US1 y US2, las
  tareas de test preceden a las de implementación y deben fallar antes de escribir el
  código que las satisface. US3 es la excepción documentada: al ser 100% configuración
  de infraestructura (Clarification #2), sus "tests" (T022-T023) validan la configuración
  aplicada, no código propio que deba fallar primero por diseño
- La tarea T017 modifica un archivo de la feature `001-worker-reportes`
  (`src/worker/reportes/service.py`); coordinar el orden de implementación entre ambas
  features si se desarrollan en paralelo por personas distintas
- Commitear después de cada tarea o grupo lógico (test rojo → implementación → test
  verde)
- Detenerse en cada checkpoint para validar la user story de forma independiente antes
  de continuar con la siguiente
