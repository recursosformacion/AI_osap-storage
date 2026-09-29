"""Superficie pública de estadísticas de catálogo (osap-storage).

Comprueba la frontera exacta: el endpoint público y la página `/statistics` quedan exentos
de service token; `/api/v1/statistics` (interno) y el resto del host siguen protegidos.
"""

from __future__ import annotations

from typing import Any

from api.dependencies import GetStatisticsDep
from api.routes.public_statistics import router
from api.security import is_exempt_path
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_exencion_por_ruta_exacta() -> None:
    assert is_exempt_path("/api/v1/public/statistics")
    assert is_exempt_path("/statistics")
    assert is_exempt_path("/api/v1/health")
    # El endpoint interno y el resto del host NO se eximen.
    assert not is_exempt_path("/api/v1/statistics")
    assert not is_exempt_path("/")
    assert not is_exempt_path("/admin")
    assert not is_exempt_path("/admin/mantenimiento")


class _Stats:
    archives = 5
    entries = 10
    files = 20
    bytes = 4_000_000_000
    computed_at = None


class _FakeUseCase:
    async def execute(self, *, refresh: bool = False) -> Any:
        return _Stats()


def test_endpoint_publico_devuelve_solo_campos_permitidos() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[GetStatisticsDep] = lambda: _FakeUseCase()
    resp = TestClient(app).get("/api/v1/public/statistics")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"archives", "entries", "files", "bytes", "computed_at"}
    assert body["archives"] == 5
    assert body["bytes"] == 4_000_000_000
    # No se exponen métricas internas ni identidad.
    assert "downloaded_tar" not in body
    assert "materialized" not in body
    assert "pending" not in body
    assert "user_id" not in body
