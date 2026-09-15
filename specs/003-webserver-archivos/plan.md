# Implementation Plan: Webserver de Acceso Restringido a Reportes

**Branch**: `003-webserver-archivos` | **Date**: 2026-09-15 | **Spec**: `specs/003-webserver-archivos/spec.md`

**Input**: Feature specification from `/specs/003-webserver-archivos/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Exponer los reportes Excel persistidos en MinIO (`002-minio-storage`) mediante un
webserver de acceso restringido: Nginx como borde HTTP, con un servicio ligero en Python
(FastAPI) que valida un JWT (firmado con secreto compartido) y consulta una tabla propia
(`reporte_autorizacion`, poblada por el worker de `001-worker-reportes`) vía el mecanismo
`auth_request` de Nginx; el contenido se sirve directamente desde MinIO usando
`X-Accel-Redirect` (Nginx hace de proxy interno, sin copiar el archivo a disco). Las
URLs usan el `solicitud_id` (UUID v4) ya existente como identificador, resistente a
enumeración. Respuestas distinguibles: `403` (no autorizado) vs `404` (inexistente).

## Technical Context

**Language/Version**: Python 3.12 (servicio de autorización), Nginx (config `nginx.conf`, sin código propio de servidor)

**Primary Dependencies**: FastAPI (servicio de autorización), `PyJWT` (validación de JWT), SQLAlchemy + `psycopg[binary]` (consulta a `reporte_autorizacion`, reutilizando la conexión de `001-worker-reportes`), `minio` (SDK, para `stat_object` de verificación de existencia), Nginx `ngx_http_auth_request_module` + `X-Accel-Redirect`

**Storage**: PostgreSQL (tabla `reporte_autorizacion`, misma base que `anuncio`/idempotencia de `001-worker-reportes`); MinIO (contenido real de los reportes, vía `002-minio-storage`, sin copia local)

**Testing**: pytest + `httpx`/`TestClient` de FastAPI (unit/contract del servicio de autorización), pruebas de integración contra Nginx real (docker-compose) + MinIO + PostgreSQL de test

**Target Platform**: Linux server (contenedor Docker), desplegado junto al resto del stack de este repo

**Project Type**: Servicio web interno (Nginx + microservicio de autorización), consumido únicamente por `api-general`, nunca directamente por frontends

**Performance Goals**: Latencia de autorización (`auth_request`) < 100ms p95 (no debe percibirse como cuello de botella frente a la descarga real del archivo); soporta descargas concurrentes del mismo reporte por el mismo usuario sin degradar (FR-010)

**Constraints**: Cero acceso público anónimo (FR-002); cero copia local del archivo persistido en MinIO (FR-007); respuestas 403/404 distinguibles sin filtrar metadata de MinIO (FR-003, FR-004); validación de JWT completamente local/stateless (sin llamada a `api-general`)

**Scale/Scope**: Mismo orden de volumen que `001`/`002` (reportes de hasta ~100k filas / decenas de MB); tráfico de descarga es bajo respecto al de generación (un archivo se descarga pocas veces por usuario autorizado)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|-----------|------------|--------|
| I. Responsabilidad Acotada | El webserver solo expone archivos ya generados/persistidos por 001/002; no envía notificaciones, no administra RabbitMQ, no decide lógica de negocio ajena | ✅ PASS |
| II. Aislamiento de Datos | La tabla `reporte_autorizacion` es una tabla **propia** de este repo (misma DB que `anuncio`, no una base ajena); no se accede a ninguna base externa nueva; no se reinterpreta el schema de `anuncio` | ✅ PASS |
| III. Contratos como Fuente Externa de Verdad | Este webserver no redefine `reporte.generar`/`reporte.listo`; el JWT es un mecanismo de autenticación de usuario final (fuera del alcance de contratos de eventos), su formato de claims se documenta en este plan pero la emisión es responsabilidad de `api-general` | ✅ PASS |
| IV. Validación Estricta de Payloads | N/A directo (no consume `reporte.generar`), pero el servicio de autorización valida estrictamente el JWT (firma, expiración, claims requeridos) antes de autorizar cualquier acceso | ✅ PASS |
| V. Acceso a Archivos Restringido | Núcleo de esta feature: cero acceso público/anónimo, validación en cada solicitud (FR-001, FR-002, FR-005) | ✅ PASS |
| VI. Feedback a `api-general` | El webserver no notifica al usuario ni coordina con Notificaciones; solo responde a la solicitud HTTP de descarga | ✅ PASS |
| VII. Test-First | TDD estricto: unit tests del servicio de autorización, contract tests del JWT/claims, integration tests contra Nginx+MinIO+Postgres reales | ✅ PASS (a aplicar en tasks.md) |
| VIII. Simplicidad | Se eligió Nginx + `auth_request` + `X-Accel-Redirect` (patrón estándar de "auth gateway" para servir archivos) en vez de servir el archivo completo a través de un proxy applicativo en Python, evitando cargar el archivo en memoria del servicio de autorización | ✅ PASS |

## Project Structure

### Documentation (this feature)

```text
specs/003-webserver-archivos/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── models/
│   └── autorizacion.py          # Modelo SQLAlchemy ReporteAutorizacion (nuevo)
├── worker/
│   ├── reportes/
│   │   └── service.py           # Extendido: registra ReporteAutorizacion tras subir_reporte()
│   └── ... (001/002, sin cambios estructurales)
└── webserver/
    ├── __init__.py
    ├── auth_service/
    │   ├── __init__.py
    │   ├── main.py               # App FastAPI, endpoint /auth (usado por auth_request)
    │   ├── jwt_validator.py       # Validacion de JWT (firma, exp, claims)
    │   ├── autorizacion_repository.py  # Consulta ReporteAutorizacion por solicitud_id + usuario
    │   └── config.py              # JWT_SECRET, DATABASE_URL, etc.
    └── config.py                  # Config compartida (endpoint MinIO, bucket) si aplica

infra/
└── nginx/
    └── nginx.conf                 # Config Nginx: auth_request + X-Accel-Redirect hacia MinIO

tests/
├── unit/
│   ├── test_jwt_validator.py
│   └── test_autorizacion_repository.py
├── contract/
│   └── test_auth_endpoint_contract.py   # Contrato del endpoint /auth (headers de entrada/salida)
└── integration/
    └── test_webserver_descarga.py       # Nginx + auth_service + MinIO + Postgres reales
```

**Structure Decision**: Se añade un nuevo subpaquete `src/webserver/auth_service/` (microservicio
FastAPI, invocado por Nginx vía `auth_request`) y `infra/nginx/nginx.conf` (configuración de
infraestructura, sin código propio de servidor HTTP de archivos). Se reutiliza la base de
datos y el patrón de modelos SQLAlchemy ya establecido por `001-worker-reportes`
(`src/models/`), agregando `ReporteAutorizacion` como nuevo modelo. `service.py` de `001`
se extiende (no se reemplaza) para registrar la autorización tras una subida exitosa a
MinIO.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Ninguna violación: todas las gates pasaron sin necesidad de justificar complejidad
adicional.

