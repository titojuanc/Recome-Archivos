"""Unit tests: jwt_validator.validar_jwt (T006)."""

from __future__ import annotations

import time

import jwt
import pytest

from src.webserver.auth_service.jwt_validator import JWTInvalido, validar_jwt

SECRET = "testing-secret"


def _token(sub="usuario-1", exp_delta=3600, secret=SECRET, algorithm="HS256"):
    payload = {"sub": sub, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_validar_jwt_acepta_token_valido_y_devuelve_sub():
    token = _token(sub="usuario-1")
    sub = validar_jwt(token, secret=SECRET)
    assert sub == "usuario-1"


def test_validar_jwt_rechaza_firma_invalida():
    token = _token(secret="otro-secreto-distinto")
    with pytest.raises(JWTInvalido):
        validar_jwt(token, secret=SECRET)


def test_validar_jwt_rechaza_token_expirado():
    token = _token(exp_delta=-10)
    with pytest.raises(JWTInvalido):
        validar_jwt(token, secret=SECRET)


def test_validar_jwt_rechaza_token_mal_formado():
    with pytest.raises(JWTInvalido):
        validar_jwt("esto-no-es-un-jwt", secret=SECRET)
