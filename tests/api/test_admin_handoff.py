from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_settings
from api.routes.pages import router


class _Validator:
    async def validate(self, token: str, scope: str) -> dict:
        assert token == "valid-service-token"
        assert scope == "storage:admin"
        return {"exp": int(time.time()) + 180}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.service_token_validator = _Validator()
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        admin_handoff_origins="https://app.openmusicrepository.com"
    )
    return TestClient(app, base_url="https://storage.openmusicrepository.com")


def test_admin_handoff_sets_short_lived_http_only_cookie_and_redirects():
    response = _client().post(
        "/admin/session",
        headers={"Origin": "https://app.openmusicrepository.com"},
        data={"token": "valid-service-token", "next": "/admin?tab=works"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin?tab=works"
    cookie = response.headers["set-cookie"].lower()
    assert "osap_storage_admin=" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=180" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_admin_handoff_rejects_untrusted_origin():
    response = _client().post(
        "/admin/session",
        headers={"Origin": "https://attacker.example"},
        data={"token": "valid-service-token"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_admin_handoff_rejects_external_redirect():
    response = _client().post(
        "/admin/session",
        headers={"Origin": "https://app.openmusicrepository.com"},
        data={"token": "valid-service-token", "next": "https://attacker.example"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_admin_handoff_rejects_missing_origin():
    response = _client().post(
        "/admin/session",
        data={"token": "valid-service-token"},
        follow_redirects=False,
    )
    assert response.status_code == 403
