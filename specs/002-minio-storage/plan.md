# Implementation Plan: Persistencia de Reportes Generados en MinIO

**Branch**: `002-minio-storage` | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-minio-storage/spec.md`

## Summary

Implementar la capa de persistencia de los archivos Excel generados por el worker de
reportes (feature `001-worker-reportes`) hacia MinIO. La ubicación del objeto se deriva
de forma determinística a partir del `solicitud_id` (UUID) de la solicitud original, de
modo que reintentos de la misma solicitud resuelvan siempre a la misma key y nunca
generen duplicados. La subida se hace de forma atómica (nunca queda un objeto parcial
accesible como si estuviera completo) y streameada desde disco/buffer para no cargar el
archivo completo en memoria. Al finalizar, se devuelve una referencia lógica
(`bucket` + `key`) que el worker incluye en el payload de `reporte.listo` (contrato ya
definido en la feature `001`). Se agrega además un proceso de limpieza por retención
configurable, que no debe interferir con descargas en curso servidas por el webserver
(feature `003-webserver-archivos`).

## Technical Context

**Language/Version**: Python 3.12 (mismo runtime que el worker de la feature `001`, esta
capa se integra como módulo interno del mismo proceso worker, no como servicio aparte)

**Primary Dependencies**: `minio` (SDK oficial de Python para MinIO/S3), reutilización de
`src/worker/reportes/excel_builder.py` de la feature `001` como productor del archivo a
persistir; `apscheduler` o un cronjob externo simple para el proceso de limpieza por
retención

**Storage**: MinIO (object storage), bucket exclusivo de este repo (Principio I/II de la
constitution); metadata de retención puede vivir como metadata del objeto en MinIO
(`X-Amz-Meta-Generado-En`) o en una tabla propia auxiliar — decisión en `research.md`

**Testing**: `pytest` + `testcontainers` (contenedor MinIO real) para tests de
integración; unit tests con el cliente MinIO mockeado para la lógica de derivación de
keys y de retención

**Target Platform**: Mismo contenedor/proceso worker que la feature `001` (módulo interno,
no un servicio HTTP independiente)

**Project Type**: Extensión de biblioteca interna del worker existente (no es un proyecto
nuevo separado)

**Performance Goals**: La subida de un archivo de hasta el volumen esperado en SC-001 de
la feature `001` (~100.000 filas) no debe agregar más de unos pocos segundos al tiempo
total ya acotado en 30s por esa feature; debe usarse streaming/multipart si el tamaño lo
amerita

**Constraints**: FR-005 (nunca exponer un objeto parcial) exige subida atómica (subir a
una key temporal y mover/confirmar, o usar la atomicidad nativa de `put_object` de
MinIO que solo publica el objeto al completarse); FR-008 exige que la limpieza por
retención no interrumpa una descarga en curso — implica que la eliminación no debe ser
agresiva/forzada sobre objetos con lectura activa

**Scale/Scope**: Un bucket (o un prefijo lógico dentro de un bucket compartido del
módulo) por tipo de artefacto (reportes); volumen esperado acorde al de la feature `001`
(miles a decenas de miles de reportes en el tiempo, sujeto a la política de retención)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Chequeo | Estado |
|---|---|---|
| I. Responsabilidad Acotada | Esta feature solo persiste y limpia archivos generados por el worker propio; no toca notificaciones, catálogo ni RabbitMQ. | ✅ PASS |
| II. Aislamiento de Datos | No introduce ningún acceso a bases de datos ajenas; MinIO es storage de objetos propio del repo, no una "base de datos ajena" en el sentido del Principio II. | ✅ PASS |
| III. Contratos como Fuente Externa de Verdad | La `referencia_archivo` incluida en `reporte.listo` respeta el schema ya definido en `001-worker-reportes/contracts/reporte.listo.schema.json`; esta feature no modifica ese contrato, solo lo completa con un valor real. | ✅ PASS |
| IV. Validación Estricta de Payloads | N/A directo (no consume eventos nuevos); reutiliza la validación ya hecha en la feature `001` antes de invocar la persistencia. | N/A |
| V. Acceso a Archivos Restringido | N/A en esta feature (el control de acceso HTTP es de `003-webserver-archivos`); esta feature solo garantiza que el bucket/credenciales de MinIO están acotados a este repo (FR-010). | ✅ PASS (parcial, se completa en `003`) |
| VI. Feedback vía `api-general` | No cambia; esta feature alimenta el mismo evento `reporte.listo` ya dirigido a `api-general`. | ✅ PASS |
| VII. Test-First | Se planifica TDD con MinIO real vía `testcontainers`, cubriendo persistencia, idempotencia y retención antes de implementar. | ✅ PASS |
| VIII. Simplicidad | Se reutiliza el mismo proceso worker en vez de introducir un servicio de persistencia separado; se prefiere la atomicidad nativa de MinIO sobre mecanismos de locking custom. | ✅ PASS |

No se detectan violaciones que requieran justificación en Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/002-minio-storage/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md         # Phase 1 output (/speckit.plan command)
├── quickstart.md         # Phase 1 output (/speckit.plan command)
├── contracts/            # Phase 1 output (/speckit.plan command)
│   └── referencia_archivo.schema.json
└── tasks.md              # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
└── worker/
    └── storage/
        ├── __init__.py
        ├── minio_client.py     # Wrapper del SDK minio: conexión, config, bucket
        ├── key_builder.py       # Derivación determinística de la key a partir de solicitud_id
        ├── persistencia.py      # Subida atómica + verificación post-subida (FR-004, FR-005)
        └── retencion.py         # Job de limpieza por política de retención (FR-007, FR-008)

tests/
├── integration/
│   ├── test_minio_persistencia.py   # Contra MinIO real (testcontainers)
│   └── test_minio_retencion.py      # Contra MinIO real, incluyendo objetos "en descarga"
└── unit/
    ├── test_key_builder.py
    └── test_retencion_logica.py      # Reglas de antigüedad sin depender de MinIO real
```

**Structure Decision**: Se agrega un nuevo submódulo `src/worker/storage/` dentro del
mismo proyecto worker de la feature `001` (no un servicio separado), reflejando que esta
feature es una extensión de responsabilidad del mismo componente ("worker" en el sentido
amplio de la constitution incluye la persistencia en MinIO como parte de generar y dejar
disponible el reporte). Se mantiene la separación entre `key_builder.py` (lógica pura,
testeable sin infraestructura), `persistencia.py` (I/O contra MinIO) y `retencion.py`
(proceso de limpieza), siguiendo el mismo patrón de capas usado en `001-worker-reportes`.

## Complexity Tracking

*Sin violaciones a justificar — tabla omitida intencionalmente.*
