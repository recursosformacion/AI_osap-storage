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
import uuid

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


def test_files_endpoint_tolerates_null_sha256(client: TestClient) -> None:
    """`files.sha256` está a NULL en toda la BBDD: la respuesta debe seguir siendo válida."""
    response = client.get("/api/v1/files", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert all("sha256" in item for item in body)

    if body:
        detail = client.get(f"/api/v1/files/{body[0]['id']}")
        assert detail.status_code == 200
        assert detail.json()["id"] == body[0]["id"]


def test_admin_works_endpoints_read_new_schema(client: TestClient) -> None:
    """Listado y detalle admin de obras: el DTO aplana `work` y sale del esquema nuevo."""
    response = client.get("/api/admin/works", params={"limit": 5, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["items"]
    first = body["items"][0]
    assert first["id"]
    assert isinstance(first["genres"], list)
    assert isinstance(first["instruments"], list)

    detail = client.get(f"/api/admin/works/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == first["id"]


def test_work_relations_add_and_remove(client: TestClient) -> None:
    """El formulario de la obra añade y quita relaciones (género) de forma reversible."""
    wid = int(_work_with_relations()["id"])
    rows = _fetch(
        "SELECT g.id FROM genres g WHERE NOT EXISTS ("
        "  SELECT 1 FROM work_genres wg WHERE wg.works_id = %s AND wg.genres_id = g.id"
        ") LIMIT 1",
        (wid,),
    )
    assert rows, "no quedan géneros sin asociar para la prueba"
    candidate = rows[0]["id"]

    before = client.get(f"/api/admin/works/{wid}/relations").json()["relations"]["genres"]
    assert candidate not in {g["ref_id"] for g in before}

    added = client.post(f"/api/admin/works/{wid}/relations/genres", json={"id": candidate})
    assert added.status_code == 200
    try:
        after = client.get(f"/api/admin/works/{wid}/relations").json()["relations"]["genres"]
        assert candidate in {g["ref_id"] for g in after}
    finally:
        removed = client.request(
            "DELETE", f"/api/admin/works/{wid}/relations/genres", json={"id": candidate}
        )
    assert removed.status_code == 200
    final = client.get(f"/api/admin/works/{wid}/relations").json()["relations"]["genres"]
    assert candidate not in {g["ref_id"] for g in final}


def test_pdmx_work_exposes_score_resource_without_representation(client: TestClient) -> None:
    """op2: PDMX no tiene nivel de edición; el recurso cuelga directamente de la obra."""
    row = _fetch(
        "SELECT works_resources_work_id AS wid FROM works_resources "
        "WHERE works_resources_file_id IS NOT NULL LIMIT 1"
    )
    assert row, "no hay recurso PDMX con fichero interno"
    wid = int(row[0]["wid"])

    work = client.get(f"/api/resource/{wid}").json()["work"]
    assert work["representations"] == []
    assert work["resources"], "el recurso debe aparecer en el array plano"
    resource = work["resources"][0]
    assert resource["available"] is True
    assert resource["links"]["download"] == f"/api/download/{resource['id']}"

    redirect = client.get(f"/api/download/{resource['id']}", follow_redirects=False)
    assert redirect.status_code in (301, 302, 307)


def test_cpdl_work_exposes_multiple_editions(client: TestClient) -> None:
    row = _fetch(
        "SELECT representations_works_id AS wid, COUNT(*) n FROM representations "
        "WHERE representations_origin='cpdl' GROUP BY representations_works_id "
        "HAVING COUNT(*) > 1 ORDER BY n DESC LIMIT 1"
    )
    assert row, "no hay obra CPDL con varias ediciones"
    wid = int(row[0]["wid"])

    work = client.get(f"/api/resource/{wid}").json()["work"]
    reps = work["representations"]
    assert len(reps) > 1
    assert all(r["origin"] == "cpdl" and r["type"] == "edition" for r in reps)
    resource = next(r for rep in reps for r in rep["resources"])
    assert resource["available"] is False
    assert resource["links"]["download"] is None


def test_search_corpus_routing(client: TestClient) -> None:
    """`/api/search` es la búsqueda general: omr+cpdl (works) y rism (rism_sources)."""
    omr = client.get("/api/search", params={"q": "bach", "corpus": "omr"}).json()
    assert "works" in omr and "rism_sources" in omr
    assert omr["rism_sources"] == []

    cpdl = client.get("/api/search", params={"q": "bach", "corpus": "cpdl"}).json()
    assert "works" in cpdl and cpdl["rism_sources"] == []

    rism = client.get("/api/search", params={"q": "bach", "corpus": "rism"}).json()
    assert rism["works"] == []
    assert isinstance(rism["rism_sources"], list)

    general = client.get("/api/search", params={"q": "bach"}).json()
    assert "works" in general and "rism_sources" in general


def test_representations_crud_endpoints(client: TestClient) -> None:
    listing = client.get("/api/admin/representations",
                         params={"origin": "cpdl", "limit": 3}).json()
    assert listing["total"] > 0 and listing["items"]
    rid = listing["items"][0]["id"]

    detail = client.get(f"/api/admin/representations/{rid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["origin"] == "cpdl"
    assert body["work"]["id"] == body["works_id"]
    assert "resources" in body and "editors" in body


def test_representation_crud_roundtrip(client: TestClient) -> None:
    work_id = int(_fetch("SELECT id FROM works LIMIT 1")[0]["id"])
    origin_id = f"test:{uuid.uuid4().hex[:12]}"

    created = client.post("/api/admin/representations", json={
        "works_id": work_id, "origin": "test", "origin_id": origin_id,
        "type": "edition", "license": "TEST",
    })
    assert created.status_code == 201, created.text
    rid = created.json()["id"]

    updated = client.put(f"/api/admin/representations/{rid}", json={
        "works_id": work_id, "origin": "test", "origin_id": origin_id,
        "type": "edition", "license": "TEST2",
    })
    assert updated.status_code == 200
    assert updated.json()["license"] == "TEST2"

    removed = client.delete(f"/api/admin/representations/{rid}")
    assert removed.json()["deleted"] == 1
    assert client.get(f"/api/admin/representations/{rid}").status_code == 404


def test_resources_crud_endpoints(client: TestClient) -> None:
    listing = client.get("/api/admin/resources",
                         params={"type": "PDF", "limit": 3}).json()
    assert listing["total"] > 0 and listing["items"]
    rid = listing["items"][0]["id"]

    detail = client.get(f"/api/admin/resources/{rid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["work"]["id"] == body["work_id"]
    # los PDF del corpus cuelgan de una representación CPDL
    assert body["representation"]["origin"] == "cpdl"


def test_resource_crud_roundtrip(client: TestClient) -> None:
    work_id = int(_fetch("SELECT id FROM works LIMIT 1")[0]["id"])
    created = client.post("/api/admin/resources", json={
        "work_id": work_id, "type": "MXL", "name": "test-roundtrip.mxl", "status": "registered",
    })
    assert created.status_code == 201, created.text
    rid = created.json()["id"]

    updated = client.put(f"/api/admin/resources/{rid}", json={
        "work_id": work_id, "type": "MXL", "name": "test-roundtrip.mxl",
        "status": "stored", "url": "https://example.org/x.mxl",
    })
    assert updated.status_code == 200
    assert updated.json()["status"] == "stored"
    assert updated.json()["url"] == "https://example.org/x.mxl"

    assert client.delete(f"/api/admin/resources/{rid}").json()["deleted"] == 1
    assert client.get(f"/api/admin/resources/{rid}").status_code == 404


def test_resolution_endpoint_returns_groups_and_rules(client: TestClient) -> None:
    row = _fetch(
        "SELECT representations_works_id AS wid FROM representations "
        "WHERE representations_origin='cpdl' GROUP BY representations_works_id "
        "HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC LIMIT 1"
    )
    assert row, "no hay obra CPDL con varias ediciones"
    wid = int(row[0]["wid"])

    response = client.get(f"/api/admin/resolution/works/{wid}")
    assert response.status_code == 200
    body = response.json()
    assert body["groups"]
    assert any(r["rule"] == "origin_identity" for r in body["applied"])
    group = body["groups"][0]
    assert group["resource_ids"]
    assert group["attributes_common"] or group["attributes_divergent"]


