# Quickstart: Persistencia de Reportes en MinIO

**Feature**: `002-minio-storage`

Esta guía describe cómo probar la persistencia en MinIO de forma local, integrándose con
un archivo Excel ya generado (mockeando o reutilizando la feature `001-worker-reportes`).

## Prerrequisitos

- Python 3.12
- Docker (para levantar MinIO local de prueba)
- `pip install minio pytest testcontainers`

## 1. Levantar MinIO local

```bash
docker run -d --name minio-test -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

Consola web disponible en `http://localhost:9001` (usuario/clave: `minioadmin`).

## 2. Crear el bucket del módulo

```bash
python - << 'PY'
from minio import Minio
client = Minio("localhost:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)
if not client.bucket_exists("recome-archivos-reportes"):
    client.make_bucket("recome-archivos-reportes")
print("Bucket listo")
PY
```

## 3. Configurar variables de entorno

```bash
export MINIO_ENDPOINT="localhost:9000"
export MINIO_ACCESS_KEY="minioadmin"
export MINIO_SECRET_KEY="minioadmin"
export MINIO_BUCKET="recome-archivos-reportes"
export MINIO_SECURE="false"
export REPORTES_DIAS_RETENCION="30"
```

## 4. Simular la persistencia de un reporte ya generado

```bash
python - << 'PY'
import io, uuid
from minio import Minio
from datetime import datetime, timezone

client = Minio("localhost:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)

anuncio_id = "anuncio-123"
solicitud_id = str(uuid.uuid4())
key = f"reportes/{anuncio_id}/{solicitud_id}.xlsx"

contenido = b"PK\x03\x04contenido-excel-de-prueba"  # stub de archivo generado por 001
stream = io.BytesIO(contenido)

result = client.put_object(
    "recome-archivos-reportes",
    key,
    stream,
    length=len(contenido),
    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    metadata={"generado-en": datetime.now(timezone.utc).isoformat()},
)
print("Persistido:", key, "etag:", result.etag)
print("referencia_archivo:", {"bucket": "recome-archivos-reportes", "key": key, "etag": result.etag})
PY
```

## 5. Verificar recuperación byte a byte (SC-003)

```bash
python - << 'PY'
from minio import Minio
client = Minio("localhost:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)
# Reemplazar KEY por la key impresa en el paso anterior
KEY = "reportes/anuncio-123/REEMPLAZAR-CON-UUID.xlsx"
resp = client.get_object("recome-archivos-reportes", KEY)
data = resp.read()
print("Bytes recuperados:", len(data))
PY
```

## 6. Probar idempotencia ante reintento (User Story 2)

Repetir el paso 4 con el **mismo** `solicitud_id` (no generar uno nuevo). Verificar que:
- La key resultante es idéntica a la primera vez.
- No se crean dos objetos distintos para la misma solicitud.

## 7. Probar el job de retención (User Story 3)

```bash
python - << 'PY'
from minio import Minio
from datetime import datetime, timedelta, timezone

client = Minio("localhost:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)

# Subir un objeto "viejo" simulando metadata de generado-en antigua
import io
old_key = "reportes/anuncio-999/viejo.xlsx"
client.put_object(
    "recome-archivos-reportes", old_key, io.BytesIO(b"viejo"), length=5,
    metadata={"generado-en": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()},
)
print("Objeto viejo subido, correr retencion.py y verificar que se elimina (retención=30 días)")
PY
```

Ejecutar el job de retención (`python -m src.worker.storage.retencion --dry-run=false`) y
confirmar que `old_key` fue eliminado, mientras que el objeto del paso 4 (reciente)
permanece.

## 8. Correr la suite de tests

```bash
pytest tests/unit
pytest tests/integration  # requiere MinIO levantado (paso 1) o vía testcontainers
```
