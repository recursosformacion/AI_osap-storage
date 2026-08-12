from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from api.security import ServiceAuthMiddleware, ServiceTokenValidator
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
from fastapi import FastAPI
from fastapi.testclient import TestClient

ISSUER = "https://auth.example"
AUDIENCE = "osap-storage"


def _make_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode()
    pub_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return priv_pem, pub_pem


def _sign(priv: str, *, scopes: str, token_use: str = "service", aud: str = AUDIENCE,
          iss: str = ISSUER, expire_in: int = 300) -> str:
    now = datetime.now(UTC)
    payload = {
        "iss": iss,
        "aud": aud,
        "exp": now + timedelta(seconds=expire_in),
        "iat": now,
        "token_use": token_use,
        "scope": scopes,
    }
    return jwt.encode(payload, priv, algorithm="RS256")


def _make_app(priv: str, pub: str) -> FastAPI:
    validator = ServiceTokenValidator(issuer=ISSUER, audience=AUDIENCE, public_key=pub)
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, validator=validator)

    @app.get("/api/search")
    async def search():
        return {"ok": True}

    @app.post("/api/v1/works/1/votes")
    async def vote():
        return {"ok": True}

    @app.post("/api/admin/composers/1/merge")
    async def merge():
        return {"ok": True}

    @app.get("/api/v1/health")
    async def health():
        return {"ok": True}

    @app.get("/metrics")
    async def metrics():
        return {"ok": True}

    return app


def test_health_and_metrics_exempt():
    priv, pub = _make_keys()
    client = TestClient(_make_app(priv, pub))
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/metrics").status_code == 200


def test_no_token_401():
    priv, pub = _make_keys()
    client = TestClient(_make_app(priv, pub))
    assert client.get("/api/search").status_code == 401


def test_read_requires_storage_read():
    priv, pub = _make_keys()
    client = TestClient(_make_app(priv, pub))
    token = _sign(priv, scopes="storage:read")
    assert client.get("/api/search", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    # Sin scope read -> 403
    token_no_scope = _sign(priv, scopes="storage:write")
    assert client.get("/api/search", headers={"Authorization": f"Bearer {token_no_scope}"}).status_code == 403


def test_write_requires_storage_write():
    priv, pub = _make_keys()
    client = TestClient(_make_app(priv, pub))
    # POST (write) sin storage:write -> 403
    read_token = _sign(priv, scopes="storage:read")
    assert client.post("/api/v1/works/1/votes", headers={"Authorization": f"Bearer {read_token}"}).status_code == 403
    # Con storage:write -> 200
    write_token = _sign(priv, scopes="storage:write")
    assert client.post("/api/v1/works/1/votes", headers={"Authorization": f"Bearer {write_token}"}).status_code == 200


def test_admin_requires_storage_admin():
    priv, pub = _make_keys()
    client = TestClient(_make_app(priv, pub))
    # El merge (admin) exige storage:admin, no basta write.
    write_token = _sign(priv, scopes="storage:write")
    resp = client.post("/api/admin/composers/1/merge",
                       headers={"Authorization": f"Bearer {write_token}"})
    assert resp.status_code == 403
    admin_token = _sign(priv, scopes="storage:admin")
    resp = client.post("/api/admin/composers/1/merge",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200


def test_user_token_rejected():
    priv, pub = _make_keys()
    client = TestClient(_make_app(priv, pub))
    user_token = _sign(priv, scopes="storage:read", token_use="user")
    assert client.get("/api/search", headers={"Authorization": f"Bearer {user_token}"}).status_code == 403


def test_expired_token_401():
    priv, pub = _make_keys()
    client = TestClient(_make_app(priv, pub))
    expired = _sign(priv, scopes="storage:read", expire_in=-60)
    assert client.get("/api/search", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_wrong_audience_401():
    priv, pub = _make_keys()
    client = TestClient(_make_app(priv, pub))
    token = _sign(priv, scopes="storage:read", aud="otro-servicio")
    assert client.get("/api/search", headers={"Authorization": f"Bearer {token}"}).status_code == 401
