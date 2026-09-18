"""Contratos de la API contra el esquema NUEVO, con BBDD real.

Levanta la app completa (FastAPI + lifespan) apuntando a la copia `osap-storage_test`
(vía `DB_NAME`) y comprueba que las respuestas del provider público y del admin salen del
modelo nuevo, comparando con SQL crudo:

- compositor de `works_person_roles` (rol 1),
- géneros de `work_genres`,
- instrumentos de `work_instruments`.

    $env:OSAP_TEST_DB = "1"; $env:OSAP_TEST_DB_NAME = "osap-storage_test"
    .venv\\Scripts\\python.exe -m pytest tests/integration -q
"""

from __future__ import annotations

import os

import pymysql
import pytest
from fastapi.testclient import TestClient
from infrastructure.config import Settings

pytestmark = pytest.mark.skipif(
    os.environ.get("OSAP_TEST_DB") != "1",
    reason="integración: requiere BBDD (define OSAP_TEST_DB=1)",
)

TEST_DB = os.environ.get("OSAP_TEST_DB_NAME", "osap-storage_test")


def _fetch(sql: str, params: tuple | None = None) -> list[dict]:
    settings = Settings()  # type: ignore[call-arg]
    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=TEST_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def _work_with_relations() -> dict:
    rows = _fetch(
        "SELECT w.id, w.works_title FROM works w "
        "WHERE EXISTS (SELECT 1 FROM work_genres g WHERE g.works_id = w.id) "
        "AND EXISTS (SELECT 1 FROM work_instruments i WHERE i.works_id = w.id) "
        "AND EXISTS (SELECT 1 FROM works_person_roles r "
        "            WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1) "
        "LIMIT 1"
    )
    assert rows, "no hay ninguna obra con compositor + género + instrumentos"
    return rows[0]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DB_NAME", TEST_DB)
    import api.main as main

    app = main.create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_version_contract(client: TestClient) -> None:
    response = client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "osap-provider-v1"


def test_health_reports_database(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] is True


def test_work_detail_reads_new_relations(client: TestClient) -> None:
    row = _work_with_relations()
    wid = int(row["id"])

    genres = {r["name"] for r in _fetch(
        "SELECT g.name FROM work_genres wg JOIN genres g ON g.id = wg.genres_id "
        "WHERE wg.works_id = %s", (wid,)
    )}
    instruments = {r["name_en"] for r in _fetch(
        "SELECT i.name_en FROM work_instruments wi JOIN instruments i ON i.id = wi.instruments_id "
        "WHERE wi.works_id = %s", (wid,)
    )}
    composer = _fetch(
        "SELECT p.persons_name AS name, p.persons_id AS id FROM works_person_roles r "
        "JOIN persons p ON p.persons_id = r.works_person_roles_person_id "
        "WHERE r.works_person_roles_work_id = %s AND r.works_person_roles_role_id = 1 "
        "ORDER BY r.works_person_roles_order, r.works_person_roles_id LIMIT 1", (wid,)
    )[0]

    response = client.get(f"/api/v1/works/{wid}")
    assert response.status_code == 200
    work = response.json()["work"]
    assert work["genres"] and set(work["genres"]) == genres
    assert work["instruments"] and set(work["instruments"]) == instruments
    assert work["person_id"] == composer["id"]
    assert work["composer"] == composer["name"]


def test_search_returns_relations(client: TestClient) -> None:
    token = str(_work_with_relations()["works_title"]).split()[0]
    response = client.get("/api/search", params={"q": token, "limit": 20})
    assert response.status_code == 200
    works = response.json()["works"]
    assert works
    assert any(w["person_id"] and w["metadata"].get("genres") for w in works)


def test_resource_metadata_lists(client: TestClient) -> None:
    wid = int(_work_with_relations()["id"])
    response = client.get(f"/api/resource/{wid}")
    assert response.status_code == 200
    metadata = response.json()["work"]["metadata"]
    assert isinstance(metadata["genres"], list) and metadata["genres"]
    assert isinstance(metadata["instruments"], list) and metadata["instruments"]


def test_admin_composers_lists_people_with_works(client: TestClient) -> None:
    response = client.get("/api/admin/composers", params={"limit": 5, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["items"]
    assert all(item["works_count"] >= 1 for item in body["items"])
