# Research: Webserver de Acceso Restringido a Reportes

**Feature**: `003-webserver-archivos`

Este documento resuelve las decisiones técnicas necesarias para el plan, dado que todas
las ambigüedades funcionales ya fueron resueltas en `spec.md` (sección Clarifications).

## 1. Patrón de servir archivos privados desde MinIO vía Nginx

**Decision**: Nginx como servidor de borde, con el módulo `ngx_http_auth_request_module`
para delegar la autorización a un subrequest interno (`/auth`, servido por el
microservicio FastAPI), y `X-Accel-Redirect` para que, una vez autorizado, Nginx
proxee directamente el objeto desde MinIO (vía un `location` interno que actúa como
reverse proxy a la API S3 de MinIO) sin que el archivo pase por el proceso Python.

**Rationale**: Es el patrón estándar ("auth gateway" / "X-Accel-Redirect pattern") para
servir archivos privados sin cargarlos en memoria de un proceso applicativo, cumpliendo
FR-007 (no copia local) y minimizando la superficie de código propio (Principio VIII).
Nginx ya es el stack definido en la constitution para el webserver de archivos.

**Alternatives considered**:
- Proxy completo en FastAPI (leer de MinIO y hacer streaming de la respuesta): más
  código propio, mayor uso de memoria/CPU en el proceso Python, sin beneficio adicional
  dado que Nginx ya resuelve esto de forma nativa y eficiente.
- URLs prefirmadas de MinIO (presigned URLs) entregadas directamente al usuario: violaría
  FR-001/FR-005 (la validación de autorización debe ocurrir en cada solicitud contra
  este repo, no delegarse a una URL de vida larga generada una sola vez) y complica la
  revocación de acceso vigente (Edge Case de revocación).

## 2. Formato y validación del JWT

**Decision**: JWT firmado con HMAC-SHA256 (`HS256`) usando un secreto compartido
(`JWT_SECRET`, variable de entorno), con claims mínimos: `sub` (usuario_solicitante),
`solicitud_id` (opcional, si el token se emite scoped a un reporte específico) y `exp`
(expiración). El microservicio de autorización valida firma y expiración con `PyJWT`,
sin ninguna llamada de red.

**Rationale**: HS256 con secreto compartido es el mecanismo más simple que cumple
"validación local y stateless" (Clarification #2); evita la complejidad de manejo de
claves públicas/privadas (RS256) cuando no hay necesidad de que terceros verifiquen el
token sin conocer el secreto — el emisor (`api-general`) y el verificador (este repo)
son ambos de confianza y pueden compartir el secreto vía configuración de despliegue.

**Alternatives considered**:
- RS256 (firma asimétrica): apropiado si `api-general` no debiera conocer un secreto
  compartido con este repo, pero agrega complejidad de gestión de claves sin beneficio
  claro en este contexto (ambos repos son del mismo sistema, coordinados vía
  constitution).
- Validación vía introspección remota (llamada a `api-general`): descartado
  explícitamente por la Clarification #2 (debe ser local/stateless).

## 3. Autorización: `auth_request` + tabla `reporte_autorizacion`

**Decision**: El endpoint `/auth` del microservicio recibe (vía headers reenviados por
Nginx desde la solicitud original) el JWT y el `solicitud_id` (extraído de la URL
`/reportes/{solicitud_id}` por Nginx y pasado como header `X-Solicitud-Id`). Valida el
JWT, extrae `usuario_solicitante` del claim `sub`, y consulta
`reporte_autorizacion` por `solicitud_id`. Si el registro no existe → `404`. Si existe
pero el `usuario_solicitante` no coincide → `403`. Si coincide → `200` (Nginx continúa
con el `X-Accel-Redirect`).

**Rationale**: Cumple exactamente las Clarifications #1 (tabla propia) y #4 (403 vs 404
distinguibles), reutilizando el patrón repository ya usado en `001-worker-reportes`
(`src/worker/reportes/repository.py`) para consistencia de estilo.

**Alternatives considered**: Ninguna — el diseño surge directamente de las
clarificaciones ya decididas; esta sección documenta la mecánica concreta de
implementación (headers, códigos de estado) no cubierta en el nivel de spec.

## 4. Extensión de `001-worker-reportes` para poblar `reporte_autorizacion`

**Decision**: `src/worker/reportes/service.py`, inmediatamente después de una llamada
exitosa a `persistencia.subir_reporte()` (T017 de `002-minio-storage`), inserta un
registro en `reporte_autorizacion` con `solicitud_id` y `usuario_solicitante` (ya
disponible en `SolicitudDeReporte`). Se inyecta como una dependencia opcional más
(`autorizacion_repository`), siguiendo el mismo patrón que `idempotencia`/`persistencia`
ya usados en esa función.

**Rationale**: Coherente con el patrón de dependency injection ya establecido en
`procesar_solicitud()`; evita acoplar `003` directamente al worker, solo extiende su
orquestación con un parámetro adicional opcional (backward-compatible con los tests ya
existentes de `001`/`002` que no lo pasan).

**Alternatives considered**: Un listener separado que reaccione a `reporte.listo`
publicado en RabbitMQ e inserte la autorización de forma asíncrona — descartado por
introducir una ventana de carrera (el reporte podría estar disponible en MinIO antes de
que exista su autorización, permitiendo un estado inconsistente), y por duplicar
infraestructura de consumo de eventos sin necesidad.

## 5. Testing de integración con Nginx real

**Decision**: Se agrega un servicio `nginx-test` a `docker-compose.test.yml`, montando
`infra/nginx/nginx.conf`, apuntando al `minio-test` y a un `auth-service-test`
(contenedor con el microservicio FastAPI) ya existentes en el mismo compose. Los tests
de integración usan `httpx`/`requests` contra `http://localhost:<puerto-test>/reportes/{id}`.

**Rationale**: Consistente con el enfoque de `001`/`002` (infraestructura real via
docker-compose para tests de integración, Principio VII); valida el comportamiento real
de `auth_request` + `X-Accel-Redirect`, que no puede mockearse fielmente a nivel unitario.

**Alternatives considered**: Testear solo el microservicio FastAPI de forma aislada (sin
Nginx real): insuficiente, ya que la lógica de `X-Accel-Redirect` y el ruteo real hacia
MinIO son parte crítica del comportamiento a validar (FR-007).
