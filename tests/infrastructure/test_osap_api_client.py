from __future__ import annotations

import asyncio

import httpx

from infrastructure.services.osap_api_client import OsapApiClient


def test_resolve_composer_calls_public_api_without_service_token(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "not_found"}

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = OsapApiClient("https://api.example/")

    result = asyncio.run(client.resolve_composer({"composer": {"name": "Mozart"}}))

    assert result == {"status": "not_found"}
    assert captured["url"] == "https://api.example/api/v1/composers/resolve"
    assert captured["json"] == {"composer": {"name": "Mozart"}}
    assert "Authorization" not in captured["headers"]
    assert captured["headers"]["Content-Type"] == "application/json"
