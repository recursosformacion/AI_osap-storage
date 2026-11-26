from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
from api.admin_session import SESSION_SCOPE, SESSION_USE, AdminSessionSigner
from api.dependencies import get_settings
from api.routes.pages import router
from api.security import SCOPE_ADMIN, ServiceAuthError, ServiceAuthMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SECRET = "test-admin-session-secret-with-enough-length-123456"


def test_issue_and_validate_roundtrip() -> None:
    signer = AdminSessionSigner(_SECRET, 3600)
    token, ttl = signer.issue(client_id="osap-api")
    assert ttl == 3600
    claims = signer.validate(token)
    assert claims is not None
    assert claims["token_use"] == SESSION_USE
    assert claims["scope"] == SESSION_SCOPE
    assert claims["client_id"] == "osap-api"
    assert signer.is_session_token(token) is True


def test_tampered_session_is_rejected() -> None:
    signer = AdminSessionSigner(_SECRET, 3600)
    token, _ = signer.issue()
    assert signer.validate(token[:-1] + ("a" if token[-1] != "a" else "b")) is None


def test_service_token_is_not_an_admin_session() -> None:
    signer = AdminSessionSigner(_SECRET, 3600)
    now = int(time.time())
    service_token = jwt.encode(
        {"token_use": "service", "scope": "storage:admin", "sub": "osap-api",
         "iat": now, "exp": now + 300},
        _SECRET,
        algorithm="HS256",
    )
    assert signer.validate(service_token) is None
    assert signer.is_session_token(service_token) is False


def test_expired_session_is_rejected() -> None:
    signer = AdminSessionSigner(_SECRET, 3600)
    now = int(time.time())
    expired = jwt.encode(
        {"token_use": SESSION_USE, "scope": SESSION_SCOPE, "sub": "storage-admin-web",
         "iat": now - 120, "exp": now - 60},
        _SECRET,
        algorithm="HS256",
    )
    assert signer.validate(expired) is None
    assert signer.is_session_token(expired) is True


class _ShortLivedValidator:
    async def validate(self, token: str, scope: str) -> dict:
        if token == "legacy-service-token":
            return {"exp": int(time.time()) + 60, "token_use": "service"}
        raise ServiceAuthError(401, "token expirado")


def _handoff_client(with_signer: bool) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.service_token_validator = _ShortLivedValidator()
    if with_signer:
        app.state.admin_session_signer = AdminSessionSigner(_SECRET, 28800)
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        admin_handoff_origins="https://app.openmusicrepository.com",
        admin_session_ttl_seconds=28800,
    )
    return TestClient(app, base_url="https://storage.openmusicrepository.com")


def test_handoff_issues_local_session_cookie_not_service_token() -> None:
    response = _handoff_client(with_signer=True).post(
        "/admin/session",
        headers={"Origin": "https://app.openmusicrepository.com"},
        data={"token": "legacy-service-token", "next": "/admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    cookie_header = response.headers["set-cookie"]
    assert "max-age=28800" in cookie_header.lower()
    cookie_value = cookie_header.split("osap_storage_admin=", 1)[1].split(";", 1)[0]
    assert cookie_value != "legacy-service-token"
    assert AdminSessionSigner(_SECRET, 28800).validate(cookie_value) is not None


def test_middleware_accepts_local_session_even_if_service_validator_would_fail() -> None:
    app = FastAPI()

    @app.get("/admin")
    async def admin() -> dict:
        return {"ok": True}

    @app.get("/api/admin/composers")
    async def admin_api() -> dict:
        return {"ok": True}

    signer = AdminSessionSigner(_SECRET, 28800)
    app.add_middleware(
        ServiceAuthMiddleware,
        validator=_ShortLivedValidator(),
        admin_sessions=signer,
    )
    token, _ = signer.issue()
    client = TestClient(app, base_url="https://storage.openmusicrepository.com")
    headers = {"cookie": f"osap_storage_admin={token}"}
    assert client.get("/admin", headers=headers).status_code == 200
    assert client.get("/api/admin/composers", headers=headers).status_code == 200
    assert client.get("/api/admin/composers").status_code == 401


def test_middleware_still_accepts_legacy_service_cookie_during_rollout() -> None:
    app = FastAPI()

    @app.get("/admin")
    async def admin() -> dict:
        return {"ok": True}

    app.add_middleware(
        ServiceAuthMiddleware,
        validator=_ShortLivedValidator(),
        admin_sessions=AdminSessionSigner(_SECRET, 28800),
    )
    client = TestClient(app, base_url="https://storage.openmusicrepository.com")
    response = client.get(
        "/admin",
        headers={"cookie": "osap_storage_admin=legacy-service-token"},
    )
    assert response.status_code == 200


def test_scope_constant_matches_session_scope() -> None:
    assert SESSION_SCOPE == SCOPE_ADMIN
