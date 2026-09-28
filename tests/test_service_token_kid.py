"""El validador de storage debe seleccionar la clave por el `kid` de la cabecera JWT.

Antes usaba `payload.get("kid")` (que no existe, el kid va en la cabecera) y caía a
`keys[0]`, por lo que con un JWKS multi-clave (rotación con solape) rechazaba los tokens
firmados con la clave anterior.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import jwt
import pytest
from api.security import ServiceAuthError, ServiceTokenValidator
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_ISS = "https://auth.osap"
_AUD = "osap-api"


def _pair() -> tuple[bytes, Any]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return private, key.public_key()


def _jwk(public_key: Any, kid: str) -> dict[str, Any]:
    from jwt.algorithms import RSAAlgorithm

    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return jwk


def _token(private_pem: bytes, kid: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": _ISS,
            "sub": "osap-api",
            "aud": _AUD,
            "jti": str(uuid.uuid4()),
            "typ": "service",
            "token_use": "service",
            "iat": now,
            "exp": now + 300,
            "scope": "storage:read",
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _validator(jwks: dict[str, Any]) -> ServiceTokenValidator:
    validator = ServiceTokenValidator(issuer=_ISS, audience=_AUD, jwks_url="http://x/jwks")

    async def _load() -> dict[str, Any]:
        return jwks

    validator._load_jwks = _load  # type: ignore[method-assign]
    return validator


def _multi_jwks() -> tuple[bytes, bytes, dict[str, Any]]:
    v1_private, v1_public = _pair()
    v2_private, v2_public = _pair()
    # v2 primero (como publica osap-auth tras la rotación): el fallback keys[0] daría v2.
    jwks = {"keys": [_jwk(v2_public, "osap-auth-v2"), _jwk(v1_public, "osap-auth-v1")]}
    return v1_private, v2_private, jwks


def test_token_de_clave_anterior_v1_valida() -> None:
    v1_private, _, jwks = _multi_jwks()
    claims = asyncio.run(
        _validator(jwks).validate(_token(v1_private, "osap-auth-v1"), "storage:read")
    )
    assert claims["iss"] == _ISS


def test_token_de_clave_nueva_v2_valida() -> None:
    _, v2_private, jwks = _multi_jwks()
    claims = asyncio.run(
        _validator(jwks).validate(_token(v2_private, "osap-auth-v2"), "storage:read")
    )
    assert claims["iss"] == _ISS


def test_kid_desconocido_rechazado() -> None:
    v1_private, _, jwks = _multi_jwks()
    with pytest.raises(ServiceAuthError):
        asyncio.run(_validator(jwks).validate(_token(v1_private, "osap-auth-x"), "storage:read"))
