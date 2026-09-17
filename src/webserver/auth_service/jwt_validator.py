"""Validacion de JWT (firma HS256, expiracion) para el microservicio de autorizacion."""

from __future__ import annotations

import jwt


class JWTInvalido(Exception):
    """Se lanza cuando el JWT es ausente, mal formado, con firma invalida o expirado."""


def validar_jwt(token: str, *, secret: str) -> str:
    """Valida el JWT y devuelve el claim `sub` (usuario) si es valido.

    Lanza `JWTInvalido` ante firma invalida, expiracion, o formato incorrecto.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise JWTInvalido(f"JWT invalido: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise JWTInvalido("JWT valido pero sin claim 'sub'")

    return sub
