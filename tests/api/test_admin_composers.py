from __future__ import annotations

import asyncio

import pytest
from api.routes import admin_composers as admin_routes
from application.use_cases.composer_admin import (
    GetComposerDetail,
    GetComposerWorks,
    ListComposers,
    MergeComposers,
)
from domain.entities.composer import Composer
from domain.services.composer_names import normalize_composer_name
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.config import Settings
from infrastructure.container import Container
from infrastructure.providers.registry import StorageBackendRegistry
from tests.fakes import (
    InMemoryArchiveEntryRepository,
    InMemoryArchiveRepository,
    InMemoryComposerRepository,
    InMemoryFileRepository,
    InMemoryJobRepository,
    InMemoryLocationRepository,
    InMemoryProviderRepository,
    InMemoryWorkRepository,
    SyncScheduler,
)

from api import errors


def _settings(tmp_path) -> Settings:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "db:\n"
        "  host: 127.0.0.1\n  port: 3306\n  user: dev\n  password: devpass\n"
        "  name: osap_storage\n  pool_size: 10\n"
        "http:\n  host: 127.0.0.1\n  port: 8000\n  public_base_url: http://storage.example\n"
        "temp_dir: /tmp\nbootstrap:\n  create_default_provider: false\n"
        "repository:\n  provider: local\n  local:\n    root: /tmp/data\n",
        encoding="utf-8",
    )
    import os

    os.environ["OSAP_CONFIG"] = str(cfg)
    os.environ.pop("OSAP_REPOSITORY_PROVIDER", None)
    return Settings()  # type: ignore[call-arg]


def _container(settings, composer_repo) -> Container:
    return Container(
        settings=settings,
        db=object(),  # type: ignore[arg-type]
        file_repo=InMemoryFileRepository(),
        provider_repo=InMemoryProviderRepository(),
        location_repo=InMemoryLocationRepository(),
        job_repo=InMemoryJobRepository(),
        archive_repo=InMemoryArchiveRepository(),
        archive_entry_repo=InMemoryArchiveEntryRepository(),
        work_repo=InMemoryWorkRepository(),
        composer_repo=composer_repo,
        composer_resolver=object(),  # type: ignore[arg-type]
        list_composers=ListComposers(composer_repo),
        get_composer_detail=GetComposerDetail(composer_repo),
        get_composer_works=GetComposerWorks(composer_repo),
        merge_composers=MergeComposers(composer_repo),
        review_composer=object(),  # type: ignore[arg-type]
        classify_composers=object(),  # type: ignore[arg-type]
        clean_composer_names=object(),  # type: ignore[arg-type]
        prune_composers=object(),  # type: ignore[arg-type]
        create_composer=object(),  # type: ignore[arg-type]
        composer_review_stats=object(),  # type: ignore[arg-type]
        voting_repo=object(),  # type: ignore[arg-type]
        catalogue_repo=object(),  # type: ignore[arg-type]
        catalogue_queries=object(),  # type: ignore[arg-type]
        record_vote=object(),  # type: ignore[arg-type]
        get_work_statistics=object(),  # type: ignore[arg-type]
        get_composer_statistics=object(),  # type: ignore[arg-type]
        refresh_voting_statistics=object(),  # type: ignore[arg-type]
        downloader=object(),  # type: ignore[arg-type]
        hasher=object(),  # type: ignore[arg-type]
        scheduler=SyncScheduler(),
        registry=StorageBackendRegistry(),
        register_file=object(),  # type: ignore[arg-type]
        get_file=object(),  # type: ignore[arg-type]
        list_files=object(),  # type: ignore[arg-type]
        start_download=object(),  # type: ignore[arg-type]
        get_download_job=object(),  # type: ignore[arg-type]
        get_download_url=object(),  # type: ignore[arg-type]
        stream_file=object(),  # type: ignore[arg-type]
        create_provider=object(),  # type: ignore[arg-type]
        get_provider=object(),  # type: ignore[arg-type]
        list_providers=object(),  # type: ignore[arg-type]
        publisher=object(),  # type: ignore[arg-type]
        import_pdmx=object(),  # type: ignore[arg-type]
        resolve_file=object(),  # type: ignore[arg-type]
        search_entries=object(),  # type: ignore[arg-type]
        materialize_archive=object(),  # type: ignore[arg-type]
        materialize_file=object(),  # type: ignore[arg-type]
        register_existing_file=object(),  # type: ignore[arg-type]
        register_resources=object(),  # type: ignore[arg-type]
        verify_file=object(),  # type: ignore[arg-type]
        delete_file=object(),  # type: ignore[arg-type]
        list_archives=object(),  # type: ignore[arg-type]
        get_archive=object(),  # type: ignore[arg-type]
        count_missing_entries=object(),  # type: ignore[arg-type]
        refresh_statistics=object(),  # type: ignore[arg-type]
        get_statistics=object(),  # type: ignore[arg-type]
        build_works=object(),  # type: ignore[arg-type]
        search_works=object(),  # type: ignore[arg-type]
        search_works_full=object(),  # type: ignore[arg-type]
        get_work=object(),  # type: ignore[arg-type]
        enrich_work=object(),  # type: ignore[arg-type]
    )


def _repo() -> InMemoryComposerRepository:
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="target", name="Wolfgang Amadeus Mozart")))
    asyncio.run(repo.create(Composer(id="source-b", name="W. A. Mozart")))
    asyncio.run(repo.create(Composer(id="source-c", name="Mozart, W. A.")))
    for cid, raw in (("target", "Wolfgang Amadeus Mozart"), ("source-b", "W. A. Mozart"),
                     ("source-c", "Mozart, W. A.")):
        asyncio.run(repo.add_alias(cid, raw, normalize_composer_name(raw)))
    for wid in (1, 2):
        repo.set_work(wid, "target", "Serenata")
    for wid in (10, 11, 12):
        repo.set_work(wid, "source-b", "Sonata")
    repo.set_work(20, "source-c", "Minuetto")
    return repo


def _app(container) -> FastAPI:
    app = FastAPI()
    app.state.container = container
    errors.register_exception_handlers(app)
    app.include_router(admin_routes.router)
    return app


@pytest.fixture
def client(tmp_path):
    repo = _repo()
    return TestClient(_app(_container(_settings(tmp_path), repo)))


def test_list_composers_paginated(client):
    resp = client.get("/api/admin/composers?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert set(body["items"][0].keys()) == {"id", "name", "status", "aliases_count", "works_count", "review_status"}


def test_list_search_by_name(client):
    resp = client.get("/api/admin/composers?q=mozart")
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


def test_list_search_by_alias(client):
    resp = client.get("/api/admin/composers?q=w. a. mozart")
    assert resp.status_code == 200
    names = {i["name"] for i in resp.json()["items"]}
    assert "W. A. Mozart" in names


def test_detail(client):
    resp = client.get("/api/admin/composers/target")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Wolfgang Amadeus Mozart"
    assert body["status"] == "active"
    assert "Wolfgang Amadeus Mozart" in body["aliases"]
    assert body["works_count"] == 2


def test_detail_not_found(client):
    assert client.get("/api/admin/composers/nope").status_code == 404


def test_works_of_composer(client):
    resp = client.get("/api/admin/composers/source-b/works?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert set(body["items"][0].keys()) == {"work_id", "title", "composer_id"}


def test_merge_and_verify(client):
    resp = client.post("/api/admin/composers/target/merge",
                       json={"source_ids": ["source-b", "source-c"]})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["sources_merged"]) == {"source-b", "source-c"}
    assert body["works_moved"] == 4
    assert body["aliases_transferred"] == 2

    detail = client.get("/api/admin/composers/target").json()
    assert detail["works_count"] == 6
    merged = client.get("/api/admin/composers/source-b").json()
    assert merged["status"] == "merged"
    assert merged["merged_into"] == "target"
    # El listado normal excluye compositores merged
    listing = client.get("/api/admin/composers").json()
    assert listing["total"] == 1


def test_merge_invalid_source_target_same(client):
    resp = client.post("/api/admin/composers/target/merge", json={"source_ids": ["target"]})
    assert resp.status_code == 400


def test_merge_missing_source(client):
    resp = client.post("/api/admin/composers/target/merge", json={"source_ids": ["missing"]})
    assert resp.status_code == 404


def test_candidates_endpoint(client):
    resp = client.get("/api/admin/composers/candidates?q=mozart")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
