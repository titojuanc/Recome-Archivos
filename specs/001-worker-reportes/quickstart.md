# Quickstart: Worker de Generación de Reportes

**Feature**: `001-worker-reportes`

Esta guía describe cómo levantar y probar el worker de forma local, de punta a punta,
sin depender de MinIO ni del webserver (features posteriores).

## Prerrequisitos

- Python 3.12
- Docker (para levantar RabbitMQ y PostgreSQL locales de prueba)
- `pip install -r requirements.txt` (pika, openpyxl, pydantic, driver SQL, pytest, etc.)

## 1. Levantar dependencias locales

```bash
docker run -d --name rabbitmq-test -p 5672:5672 -p 15672:15672 rabbitmq:3-management
docker run -d --name postgres-reportes -p 5432:5432 \
  -e POSTGRES_DB=reportes -e POSTGRES_USER=reportes -e POSTGRES_PASSWORD=reportes \
  postgres:16
```

## 2. Preparar el esquema de prueba (tabla `anuncio` simplificada)

```sql
CREATE TABLE anuncio (
    id UUID PRIMARY KEY,
    anuncio_id TEXT NOT NULL,
    tipo_evento TEXT NOT NULL CHECK (tipo_evento IN ('impresion', 'click')),
    timestamp TIMESTAMPTZ,
    usuario_id TEXT
);

CREATE TABLE registro_idempotencia (
    solicitud_id UUID PRIMARY KEY,
    estado TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    completado_en TIMESTAMPTZ
);

INSERT INTO anuncio (id, anuncio_id, tipo_evento, timestamp, usuario_id) VALUES
  (gen_random_uuid(), 'anuncio-123', 'impresion', now() - interval '2 days', 'user-1'),
  (gen_random_uuid(), 'anuncio-123', 'click',     now() - interval '1 day',  'user-1'),
  (gen_random_uuid(), 'anuncio-123', 'impresion', NULL,                     NULL);
```

## 3. Configurar variables de entorno del worker

```bash
export RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
export DATABASE_URL="postgresql://reportes:reportes@localhost:5432/reportes"
export QUEUE_REPORTE_GENERAR="reporte.generar"
export QUEUE_REPORTE_LISTO="reporte.listo"
```

## 4. Correr el worker

```bash
python -m src.worker.main
```

## 5. Publicar un evento de prueba (`reporte.generar`)

```bash
python - << 'PY'
import pika, json, uuid
conn = pika.BlockingConnection(pika.URLParameters("amqp://guest:guest@localhost:5672/"))
ch = conn.channel()
ch.queue_declare(queue="reporte.generar", durable=True)
payload = {
    "solicitud_id": str(uuid.uuid4()),
    "anuncio_id": "anuncio-123",
    "fecha_desde": "2020-01-01T00:00:00Z",
    "fecha_hasta": "2030-01-01T00:00:00Z",
    "usuario_solicitante": "user-1"
}
ch.basic_publish(exchange="", routing_key="reporte.generar", body=json.dumps(payload))
print("Evento publicado:", payload)
PY
```

## 6. Verificar el resultado

- El worker debe loguear la validación exitosa del payload.
- Debe generarse un archivo Excel local (o en el path configurado como stub de
  persistencia, ya que MinIO no es parte de esta feature) con dos hojas: `Impresiones` y
  `Clicks`.
- El registro con `timestamp` nulo debe aparecer en la hoja `Impresiones` con el campo
  correspondiente marcado como `"N/D"`.
- Debe publicarse un mensaje en la cola `reporte.listo` con `solicitud_id` igual al
  enviado y `estado: "generado"`.

## 7. Probar el camino de rechazo

Repetir el paso 5 omitiendo `anuncio_id` en el payload. El worker debe:
- Rechazar el mensaje (nack) sin generar archivo.
- No publicar ningún evento en `reporte.listo`.
- Enrutar el mensaje a la cola/exchange de dead-letter configurada.

## 8. Correr la suite de tests

```bash
pytest tests/unit tests/contract
pytest tests/integration  # requiere RabbitMQ y PostgreSQL levantados (pasos 1-2)
```
