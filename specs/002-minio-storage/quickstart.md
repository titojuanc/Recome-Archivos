# Quickstart: Persistencia de Reportes en MinIO

**Feature**: `002-minio-storage`

Esta guía describe cómo probar la persistencia en MinIO de forma local, usando el
código real implementado en `src/worker/storage/` (`key_builder.py`, `minio_client.py`,
`persistencia.py`), integrado con `001-worker-reportes`.

> Nota de implementación: la imagen `minio/minio` de Docker Hub puede requerir
> autenticación en algunos entornos; el `docker-compose.test.yml` de este repo usa
> `quay.io/minio/minio` como mirror equivalente.

## Prerrequisitos

- Python 3.12 (entorno virtual en `.venv/`)
- Docker + Docker Compose
- Dependencias instaladas: `pip install -e .` (incluye `minio` vía `pyproject.toml`)

## 1. Levantar la infraestructura de test (RabbitMQ + PostgreSQL + MinIO)

```bash
docker compose -f docker-compose.test.yml up -d
docker compose -f docker-compose.test.yml ps
```

Servicios y puertos (host):
- MinIO API: `localhost:9002` (interno 9000), consola: `localhost:9091`
- PostgreSQL: `localhost:5433`
- RabbitMQ: `localhost:5673` (management UI: `localhost:15673`)

Credenciales de test de MinIO: `reportes-test` / `reportes-test-secret`.

## 2. Configurar variables de entorno

```bash
export MINIO_ENDPOINT="localhost:9002"
export MINIO_ACCESS_KEY="reportes-test"
export MINIO_SECRET_KEY="reportes-test-secret"
export MINIO_BUCKET="reportes-test"
export MINIO_SECURE="false"
```

(En tests de integración, estas mismas variables tienen el prefijo `TEST_`, ej.
`TEST_MINIO_ENDPOINT`, con los mismos valores por defecto.)

## 3. Crear el bucket y subir un reporte de prueba

```bash
python - << 'PY'
import io
from src.worker.storage.minio_client import crear_cliente_minio, asegurar_bucket
from src.worker.storage.persistencia import subir_reporte

client = crear_cliente_minio(
    endpoint="localhost:9002",
    access_key="reportes-test",
    secret_key="reportes-test-secret",
    secure=False,
)
asegurar_bucket(client, "reportes-test")

contenido = b"PK\x03\x04contenido-excel-de-prueba"  # stub de archivo generado por 001
referencia = subir_reporte(
    "anuncio-123", "solicitud-demo-1", io.BytesIO(contenido),
    client=client, bucket="reportes-test",
)
print("Persistido:", referencia)
PY
```

`subir_reporte()` calcula un checksum local (MD5), sube el archivo vía `put_object`, y
verifica de forma **bloqueante** que el ETag devuelto coincide con el checksum antes de
devolver la `ReferenciaDeArchivo` (FR-004). Si no coincide, lanza `FalloDePersistencia`.

## 4. Verificar recuperación byte a byte (SC-003)

```bash
python - << 'PY'
from src.worker.storage.minio_client import crear_cliente_minio
client = crear_cliente_minio(
    endpoint="localhost:9002", access_key="reportes-test",
    secret_key="reportes-test-secret", secure=False,
)
resp = client.get_object("reportes-test", "reportes/anuncio-123/solicitud-demo-1.xlsx")
data = resp.read()
print("Bytes recuperados:", len(data))
PY
```

## 5. Probar idempotencia ante reintento (User Story 2)

Repetir el paso 3 con el **mismo** `anuncio_id`/`solicitud_id`. `subir_reporte()` no
hace ningún chequeo previo de existencia: simplemente sobrescribe el objeto bajo la
misma key determinística (FR-006), sin crear objetos adicionales.

## 6. Configurar y probar la lifecycle rule de retención (User Story 3)

La retención se implementa **exclusivamente** como configuración nativa de MinIO
(lifecycle rules), sin código propio de limpieza (Clarification #2). La definición vive
en `infra/minio/lifecycle-rules.json` y se aplica con
`src.worker.storage.minio_client.aplicar_lifecycle_rules(client, bucket, reglas)`, o
manualmente vía `mc`:

```bash
mc alias set local http://localhost:9002 reportes-test reportes-test-secret
mc ilm rule add local/reportes-test --expire-days 30 --prefix "reportes/"
mc ilm rule ls local/reportes-test
```

## 7. Correr la suite de tests

```bash
.venv/bin/python -m pytest tests/unit tests/contract
.venv/bin/python -m pytest tests/integration  # requiere docker-compose.test.yml arriba (paso 1)
```
