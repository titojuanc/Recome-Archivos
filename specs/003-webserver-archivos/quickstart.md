# Quickstart: Webserver de Acceso Restringido a Reportes

**Feature**: `003-webserver-archivos`

Esta guía valida de punta a punta el flujo de descarga autorizada de un reporte, usando
la infraestructura real (Nginx + MinIO + PostgreSQL) definida en `docker-compose.test.yml`.

## Prerrequisitos

- Servicios de `001-worker-reportes` y `002-minio-storage` ya implementados y con un
  reporte de prueba persistido en MinIO (ver sus respectivos quickstarts).
- Un registro en `reporte_autorizacion` para ese reporte (creado automáticamente por el
  worker tras `subir_reporte()`, o insertado manualmente para pruebas).
- Variables de entorno: `JWT_SECRET` (compartido entre el emisor de prueba y el servicio
  de autorización), `DATABASE_URL` (misma base que `001`).

## 1. Levantar la infraestructura de test

```bash
docker compose -f docker-compose.test.yml up -d
```

Servicios relevantes para esta feature (nuevos, a agregar en Setup de tasks.md):
- `auth-service-test`: microservicio FastAPI de autorización.
- `nginx-test`: Nginx con `infra/nginx/nginx.conf`, puerto expuesto ej. `8080`.

## 2. Generar un JWT de prueba

```bash
python - << 'PY'
import jwt, time
secret = "testing-secret"  # debe coincidir con JWT_SECRET del auth-service-test
token = jwt.encode(
    {"sub": "usuario-1", "exp": int(time.time()) + 3600},
    secret,
    algorithm="HS256",
)
print(token)
PY
```

## 3. Insertar un registro de autorización de prueba

```bash
python - << 'PY'
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.models.autorizacion import ReporteAutorizacion

engine = create_engine("postgresql+psycopg://reportes:reportes@localhost:5433/reportes")
with Session(engine) as session:
    session.add(ReporteAutorizacion(
        solicitud_id="00000000-0000-0000-0000-000000000001",
        anuncio_id="anuncio-123",
        usuario_solicitante="usuario-1",
        bucket="reportes-test",
        key="reportes/anuncio-123/00000000-0000-0000-0000-000000000001.xlsx",
    ))
    session.commit()
PY
```

## 4. Descargar el reporte con el usuario autorizado (200)

```bash
curl -i -H "Authorization: Bearer <TOKEN_DEL_PASO_2>" \
  http://localhost:8080/reportes/00000000-0000-0000-0000-000000000001
```

Debe responder `200` con el contenido del Excel.

## 5. Verificar rechazo para un usuario no autorizado (403)

Generar un JWT con `"sub": "usuario-2"` y repetir la solicitud del paso 4: debe responder
`403` sin contenido.

## 6. Verificar rechazo sin credenciales (401)

```bash
curl -i http://localhost:8080/reportes/00000000-0000-0000-0000-000000000001
```

Debe responder `401`.

## 7. Verificar reporte inexistente (404)

```bash
curl -i -H "Authorization: Bearer <TOKEN_DEL_PASO_2>" \
  http://localhost:8080/reportes/00000000-0000-0000-0000-000000000099
```

Debe responder `404`, sin exponer detalles de MinIO.

> **Nota de implementación**: el módulo `auth_request` de Nginx solo reconoce de forma
> nativa los códigos `200`/`401`/`403` en la respuesta del subrequest `/auth`; cualquier
> otro código (como un `404` literal) termina en un `500` genérico de Nginx. Por eso
> `/auth` expone el caso "no encontrado" como `403` + header `X-Auth-Reason: not_found`,
> y `infra/nginx/nginx.conf` lo traduce al `404` real que ve el cliente final (ver
> `location @denied` en el config). Asimismo, dado que Nginx proxea directamente a MinIO
> tras la autorización (sin firmar solicitudes S3/SigV4), el bucket de test requiere una
> política de lectura anónima aplicada vía
> `src.worker.storage.minio_client.aplicar_politica_lectura_interna()` — segura porque
> MinIO nunca se expone directamente al cliente, solo a través de Nginx (que ya exige
> `auth_request`).

## 8. Correr la suite de tests

```bash
.venv/bin/python -m pytest tests/unit tests/contract
.venv/bin/python -m pytest tests/integration/test_webserver_descarga.py  # requiere paso 1
```
