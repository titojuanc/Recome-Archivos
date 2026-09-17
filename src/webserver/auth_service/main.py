"""Microservicio FastAPI de autorizacion, invocado por Nginx via auth_request.

Endpoint GET /auth: valida el JWT del header Authorization y el X-Solicitud-Id,
consulta ReporteAutorizacion, y responde 200 (+ headers X-Bucket/X-Object-Key), 401,
403 o 404 segun corresponda (ver data-model.md).
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.webserver.auth_service.autorizacion_repository import obtener_autorizacion
from src.webserver.auth_service.config import Config
from src.webserver.auth_service.jwt_validator import JWTInvalido, validar_jwt

app = FastAPI()

_config = Config.from_env()
_engine = create_engine(_config.database_url)
SessionLocal = sessionmaker(bind=_engine)


@app.get("/auth")
def auth(
    response: Response,
    authorization: str | None = Header(default=None),
    x_solicitud_id: str | None = Header(default=None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="credenciales ausentes o mal formadas")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        usuario = validar_jwt(token, secret=_config.jwt_secret)
    except JWTInvalido:
        raise HTTPException(status_code=401, detail="credenciales invalidas")

    # Nota: el modulo auth_request de Nginx solo trata de forma nativa los codigos
    # 200/401/403 devueltos por el subrequest; cualquier otro codigo (ej. 404) se
    # traduce en un 500 generico. Por eso el caso "no encontrado" tambien se expone
    # como 403, distinguido via el header X-Auth-Reason, que Nginx usa para decidir
    # el codigo final que ve el cliente (ver infra/nginx/nginx.conf).
    if not x_solicitud_id:
        raise HTTPException(
            status_code=403,
            detail="solicitud_id no provisto",
            headers={"X-Auth-Reason": "not_found"},
        )

    with SessionLocal() as session:
        autorizacion = obtener_autorizacion(session, x_solicitud_id)

    if autorizacion is None:
        raise HTTPException(
            status_code=403,
            detail="reporte no encontrado",
            headers={"X-Auth-Reason": "not_found"},
        )

    if autorizacion.usuario_solicitante != usuario:
        raise HTTPException(
            status_code=403,
            detail="usuario no autorizado",
            headers={"X-Auth-Reason": "forbidden"},
        )

    response.headers["X-Bucket"] = autorizacion.bucket
    response.headers["X-Object-Key"] = autorizacion.key
    return {"status": "authorized"}
