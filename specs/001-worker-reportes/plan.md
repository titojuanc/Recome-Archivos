# Implementation Plan: Worker de Generación de Reportes (Excel) + Modelo SQL de Anuncios

**Branch**: `001-worker-reportes` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-worker-reportes/spec.md`

## Summary

Implementar un worker Python que consume el evento `reporte.generar` desde el RabbitMQ
compartido del sistema, valida el payload contra el schema documentado en `api-general`,
consulta la tabla SQL `anuncio` (impresiones/clicks, compartida con `api-general`) para
el `anuncio_id` y rango de fechas solicitados, genera un archivo Excel con dos hojas
(impresiones y clicks) — marcando con "N/D" los campos incompletos/corruptos en lugar de
excluir registros — y publica el evento `reporte.listo` con la referencia lógica al
archivo generado. El worker es idempotente por el UUID de solicitud generado por
`api-general`, procesa mensajes de forma concurrente dentro de una única instancia
(async/threads, sin escalado horizontal), soporta rangos de fechas sin límite mediante
consulta/escritura incremental, y nunca hace ack de un mensaje hasta confirmar éxito
completo (generación + publicación de feedback). El acceso a MinIO y la exposición HTTP
del archivo quedan explícitamente fuera de esta feature.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: `pika` (cliente RabbitMQ), `openpyxl` (escritura Excel en modo
streaming/`write_only`), un driver SQL async o sync según el motor elegido (`psycopg`/
`SQLAlchemy` sobre PostgreSQL), `pydantic` (validación de payloads de eventos contra el
schema documentado en `api-general`)

**Storage**: Base de datos SQL de reportes con la tabla `anuncio` (motor: PostgreSQL,
compartida por diseño con `api-general` según Principio II de la constitution)

**Testing**: `pytest` + `pytest-asyncio` (si se usa concurrencia async) para TDD de la
lógica propia; contract tests contra los schemas JSON de `reporte.generar`/`reporte.listo`
documentados en `api-general`; tests de integración contra una instancia real/dockerizada
de RabbitMQ y de la base de datos de reportes (vía `testcontainers` o equivalente)

**Target Platform**: Contenedor Linux (Docker), desplegado como proceso worker de larga
duración (no request/response)

**Project Type**: Servicio worker standalone (consumidor/productor de eventos), sin
interfaz HTTP propia en esta feature

**Performance Goals**: Generar y publicar `reporte.listo` en menos de 30s para hasta
100.000 registros (SC-001); sostener 50 solicitudes concurrentes en una única instancia
sin pérdida de eventos (SC-004, FR-012)

**Constraints**: Sin límite máximo de rango de fechas (FR-011) → consulta y escritura de
Excel deben ser incrementales (cursor/streaming, `openpyxl` en modo `write_only`) para
evitar agotar memoria; ack manual (no automático) para garantizar at-least-once sin
pérdida (FR-007); idempotencia obligatoria por UUID de solicitud (FR-008)

**Scale/Scope**: Un único worker (proceso), tabla `anuncio` con volumen esperado de miles
a cientos de miles de filas por reporte individual; sin procesamiento distribuido tipo
big data (ver Assumptions del spec)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Chequeo | Estado |
|---|---|---|
| I. Responsabilidad Acotada | Esta feature solo genera el Excel a partir de `anuncio` y publica el evento de feedback; no toca notificaciones, no despliega RabbitMQ, no expone HTTP. | ✅ PASS |
| II. Aislamiento de Datos (única excepción) | El worker accede únicamente a la tabla `anuncio`, excepción ya documentada en la constitution; no se toca ninguna otra base del sistema. | ✅ PASS |
| III. Contratos como Fuente Externa de Verdad | El schema de `reporte.generar`/`reporte.listo` y de `anuncio` se toman como documentados en `api-general`; el plan no redefine estos contratos, solo los implementa (ver `contracts/` en Phase 1). | ✅ PASS (dependiente de que la documentación en `api-general` exista/se mantenga sincronizada — riesgo a seguir en Phase 0) |
| IV. Validación Estricta de Payloads | FR-001/FR-002 exigen validar contra schema antes de procesar y rechazar sin adivinar valores por defecto. | ✅ PASS |
| V. Acceso a Archivos Restringido | No aplica a esta feature (el webserver es la feature `003-webserver-archivos`); este worker no expone archivos. | N/A en esta feature |
| VI. Feedback vía `api-general` | El worker publica `reporte.listo` hacia `api-general`, sin hablar directo con el usuario ni con Notificaciones. | ✅ PASS |
| VII. Test-First | Se planifica TDD (pytest) + contract tests + integración contra broker/DB reales antes de cualquier deploy. | ✅ PASS (a verificar en fase de tasks) |
| VIII. Simplicidad | Un solo proceso, concurrencia interna simple (async/threads) en vez de orquestación distribuida; sin excepciones nuevas de acceso a datos. | ✅ PASS |

No se detectan violaciones que requieran justificación en Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-worker-reportes/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── reporte.generar.schema.json
│   └── reporte.listo.schema.json
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── worker/
│   ├── __init__.py
│   ├── main.py               # Entry point: conexión a RabbitMQ, loop de consumo
│   ├── config.py             # Configuración (env vars: conexión RabbitMQ, DB, colas)
│   ├── events/
│   │   ├── consumer.py       # Consumo de reporte.generar, ack/nack, dead-letter
│   │   ├── publisher.py      # Publicación de reporte.listo
│   │   └── schemas.py        # Modelos pydantic reflejando los contratos de api-general
│   ├── reportes/
│   │   ├── repository.py     # Acceso a la tabla anuncio (queries por anuncio_id + rango)
│   │   ├── excel_builder.py  # Generación del Excel (hojas impresiones/clicks, N/D)
│   │   └── service.py        # Orquestación: validar → consultar → generar → publicar
│   └── idempotencia/
│       └── store.py          # Registro de solicitudes ya procesadas (por UUID)
└── models/
    └── anuncio.py             # Modelo de datos de la tabla anuncio compartida

tests/
├── contract/
│   ├── test_reporte_generar_schema.py
│   └── test_reporte_listo_schema.py
├── integration/
│   ├── test_worker_rabbitmq.py     # Contra broker real/dockerizado
│   ├── test_worker_db_anuncio.py   # Contra DB real/dockerizada
│   └── test_flujo_end_to_end.py    # Evento → Excel → evento de feedback
└── unit/
    ├── test_excel_builder.py
    ├── test_repository.py
    └── test_idempotencia.py
```

**Structure Decision**: Proyecto único tipo servicio worker (Opción 1 del template,
adaptada). No aplica separación backend/frontend ni mobile/API porque esta feature no
expone ninguna interfaz de usuario ni HTTP; es un consumidor/productor de eventos con
acceso a una única tabla SQL. La estructura separa claramente `events/` (contratos e
I/O de RabbitMQ), `reportes/` (lógica de negocio propia: consulta + generación de Excel)
e `idempotencia/` (control de duplicados), reflejando los principios de responsabilidad
acotada y contratos externos de la constitution.

## Complexity Tracking

*Sin violaciones a justificar — tabla omitida intencionalmente.*
