"""Filtro de visibilidad del listado admin de Composer (visible|hidden|all).

Cubre: filtro visible/hidden/all, búsqueda combinada, ausencia de mutación,
selección de no visibles para fusión y comportamiento estable de los visibles.
"""

from __future__ import annotations

import asyncio

import pytest
from domain.entities.composer import Composer, ComposerStatus
from domain.services.composer_names import normalize_composer_name
from fastapi.testclient import TestClient
from tests.api.test_admin_composers import _app, _container, _settings
from tests.fakes import InMemoryComposerRepository


def _repo() -> InMemoryComposerRepository:
    repo = InMemoryComposerRepository()
    # visibles
    asyncio.run(repo.create(Composer(id="v-a", name="Juli Garreta i Arboix", visible=True)))
    asyncio.run(repo.create(Composer(id="v-b", name="Mozart, Wolfgang Amadeus", visible=True)))
    # candidato no visible
    asyncio.run(repo.create(Composer(
        id="h-c", name="Juli Garreta", visible=False, status="candidate",
        review_status="review_required")))
    # fusionado no visible
    asyncio.run(repo.create(Composer(
        id="m-d", name="Garreta, Juli", visible=False,
        status=ComposerStatus.MERGED, merged_into="v-a")))
    for cid, raw in (("v-a", "Juli Garreta i Arboix"), ("v-b", "Mozart, Wolfgang Amadeus"),
                     ("h-c", "Juli Garreta"), ("m-d", "Garreta, Juli")):
        asyncio.run(repo.add_alias(cid, raw, normalize_composer_name(raw)))
    return repo


@pytest.fixture
def client(tmp_path):
    repo = _repo()
    return TestClient(_app(_container(_settings(tmp_path), repo)))


def _ids(resp) -> list[str]:
    return [i["id"] for i in resp.json()["items"]]


def test_default_list_solo_visibles(client):
    resp = client.get("/api/admin/composers?limit=50&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert set(_ids(resp)) == {"v-a", "v-b"}


def test_visible_filtro_explicito(client):
    resp = client.get("/api/admin/composers?visible=visible&limit=50&offset=0")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
    assert set(_ids(resp)) == {"v-a", "v-b"}


def test_hidden_solo_no_visibles(client):
    resp = client.get("/api/admin/composers?visible=hidden&limit=50&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert set(_ids(resp)) == {"h-c", "m-d"}
    by_id = {i["id"]: i for i in body["items"]}
    assert by_id["h-c"]["visible"] is False
    assert by_id["m-d"]["visible"] is False


def test_all_incluye_visibles_y_no_visibles(client):
    resp = client.get("/api/admin/composers?visible=all&limit=50&offset=0")
    assert resp.status_code == 200
    assert resp.json()["total"] == 4
    assert set(_ids(resp)) == {"v-a", "v-b", "h-c", "m-d"}


def test_busqueda_combinada_con_cada_filtro(client):
    r1 = client.get("/api/admin/composers?visible=visible&q=Garreta")
    assert {i["name"] for i in r1.json()["items"]} == {"Juli Garreta i Arboix"}

    r2 = client.get("/api/admin/composers?visible=hidden&q=Garreta")
    assert {i["name"] for i in r2.json()["items"]} == {"Juli Garreta", "Garreta, Juli"}

    r3 = client.get("/api/admin/composers?visible=all&q=Garreta")
    assert {i["name"] for i in r3.json()["items"]} == {
        "Juli Garreta i Arboix", "Juli Garreta", "Garreta, Juli"}


def test_cambiar_filtro_no_modifica_bd(tmp_path):
    repo = _repo()
    app = _app(_container(_settings(tmp_path), repo))
    client = TestClient(app)
    before = {c.id: (c.visible, c.status) for c in repo._composers.values()}
    for scope in ("visible", "hidden", "all", "visible"):
        for _ in range(2):
            client.get(f"/api/admin/composers?visible={scope}&q=Garreta")
    after = {c.id: (c.visible, c.status) for c in repo._composers.values()}
    assert after == before


def test_no_visibles_seleccionables_para_fusion(tmp_path):
    repo = _repo()
    client = TestClient(_app(_container(_settings(tmp_path), repo)))
    # el target puede ser un candidato no visible y el source un visible
    resp = client.post("/api/admin/composers/v-b/merge", json={"source_ids": ["h-c"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sources_merged"] == ["h-c"]
    # h-c quedó merged hacia v-b (no visible en el listado 'hidden' como merged)
    hidden = client.get("/api/admin/composers?visible=hidden").json()["items"]
    hc = next(i for i in hidden if i["id"] == "h-c")
    assert hc["status"] == "merged"


def test_visibles_comportamiento_previo(client):
    """El listado por defecto devuelve exactamente lo mismo que antes (visibles)."""
    resp = client.get("/api/admin/composers?limit=50&offset=0")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["visible"] is True for i in items)
    assert all(i["status"] == "active" for i in items)
