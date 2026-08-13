from __future__ import annotations

import asyncio

import pytest
from api.routes import catalogues as cat_routes
from application.use_cases.catalogues import CatalogueQueries
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.seed.catalogues import CATALOGUES
from tests.fakes import InMemoryCatalogueRepository


@pytest.fixture
def client():
    repo = InMemoryCatalogueRepository()
    asyncio.run(repo.seed(CATALOGUES))
    app = FastAPI()
    app.state.catalogue_queries = CatalogueQueries(repo)
    app.dependency_overrides = {}
    from api.dependencies import CatalogueQueriesDep

    app.dependency_overrides[CatalogueQueriesDep] = lambda: app.state.catalogue_queries
    app.include_router(cat_routes.router)
    return TestClient(app)


def test_catalogues_by_prefix(client):
    r = client.get("/api/v1/catalogues?prefix=BWV")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["composer"] == "Johann Sebastian Bach"
    assert data[0]["catalogue_name"] == "Bach-Werke-Verzeichnis"


def test_catalogues_by_composer(client):
    r = client.get("/api/v1/catalogues?composer=Mozart")
    assert r.status_code == 200
    data = r.json()
    assert data
    assert all("mozart" in c["composer"].lower() for c in data)


def test_catalogues_list(client):
    r = client.get("/api/v1/catalogues?limit=5")
    assert r.status_code == 200
    assert len(r.json()) == 5


def test_catalogues_keys(client):
    r = client.get("/api/v1/catalogues?prefix=K")
    assert r.status_code == 200
    item = r.json()[0]
    assert set(item.keys()) == {"id", "prefix", "composer", "catalogue_name",
                                "creator", "ordering_criterion", "created_at"}
