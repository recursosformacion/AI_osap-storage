from __future__ import annotations

import asyncio

import pytest
from api.routes import provider as provider_routes
from application.use_cases.works import GetWork, SearchWorks, SearchWorksFull
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.composer import Composer
from domain.entities.storage_provider import ProviderType
from domain.entities.work import Work
from domain.services.composer_names import normalize_composer_name
from domain.services.composer_resolver import ComposerResolver
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
    MemoryBackend,
    SyncScheduler,
)

from api import errors


def _settings(tmp_path) -> Settings:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "db:\n"
        "  host: 127.0.0.1\n"
        "  port: 3306\n"
        "  user: dev\n"
        "  password: devpass\n"
        "  name: osap_storage\n"
        "  pool_size: 10\n"
        "http:\n"
        "  host: 127.0.0.1\n"
        "  port: 8000\n"
        "  public_base_url: http://storage.example\n"
        "temp_dir: /tmp\n"
        "bootstrap:\n"
        "  create_default_provider: false\n"
        "repository:\n"
        "  provider: local\n"
        "  local:\n"
        "    root: /tmp/data\n",
        encoding="utf-8",
    )
    import os

    os.environ["OSAP_CONFIG"] = str(cfg)
    os.environ.pop("OSAP_REPOSITORY_PROVIDER", None)
    return Settings()  # type: ignore[call-arg]


def _registry() -> StorageBackendRegistry:
    reg = StorageBackendRegistry()
    reg.register(ProviderType.LOCAL_DISK, MemoryBackend)
    return reg


def _build_container(settings: Settings, work_repo: InMemoryWorkRepository,
                     entry_repo: InMemoryArchiveEntryRepository,
                     composer_repo: InMemoryComposerRepository | None = None) -> Container:
    file_repo = InMemoryFileRepository()
    provider_repo = InMemoryProviderRepository()
    location_repo = InMemoryLocationRepository()
    job_repo = InMemoryJobRepository()
    archive_repo = InMemoryArchiveRepository()
    registry = _registry()
    composer_repo = composer_repo or InMemoryComposerRepository()
    composer_resolver = ComposerResolver(composer_repo)
    return Container(
        settings=settings,
        db=object(),  # type: ignore[arg-type]
        file_repo=file_repo,
        provider_repo=provider_repo,
        location_repo=location_repo,
        job_repo=job_repo,
        archive_repo=archive_repo,
        archive_entry_repo=entry_repo,
        work_repo=work_repo,
        composer_repo=composer_repo,
        composer_resolver=composer_resolver,
        list_composers=object(),  # type: ignore[arg-type]
        get_composer_detail=object(),  # type: ignore[arg-type]
        get_composer_works=object(),  # type: ignore[arg-type]
        merge_composers=object(),  # type: ignore[arg-type]
        review_composer=object(),  # type: ignore[arg-type]
        classify_composers=object(),  # type: ignore[arg-type]
        clean_composer_names=object(),  # type: ignore[arg-type]
        prune_composers=object(),  # type: ignore[arg-type]
        create_composer=object(),  # type: ignore[arg-type]
        composer_review_stats=object(),  # type: ignore[arg-type]
        voting_repo=object(),  # type: ignore[arg-type]
        record_vote=object(),  # type: ignore[arg-type]
        get_work_statistics=object(),  # type: ignore[arg-type]
        get_composer_statistics=object(),  # type: ignore[arg-type]
        refresh_voting_statistics=object(),  # type: ignore[arg-type]
        downloader=object(),  # type: ignore[arg-type]
        hasher=object(),  # type: ignore[arg-type]
        scheduler=SyncScheduler(),
        registry=registry,
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
        search_works=SearchWorks(work_repo, composer_resolver),
        search_works_full=SearchWorksFull(work_repo, entry_repo, composer_resolver),
        get_work=GetWork(work_repo, entry_repo, composer_resolver),
        enrich_work=object(),  # type: ignore[arg-type]
    )


def _seed_composer(composer_repo: InMemoryComposerRepository) -> str:
    composer = asyncio.run(composer_repo.create(Composer(id="8f5b3a7e", name="Wolfgang Amadeus Mozart")))
    for alias in ("Mozart", "Mozart, W. A.", "W. A. Mozart", "Wolfgang Amadeus Mozart"):
        asyncio.run(composer_repo.add_alias(composer.id, alias, normalize_composer_name(alias)))
    return composer.id


def _seed(work_repo: InMemoryWorkRepository, entry_repo: InMemoryArchiveEntryRepository) -> None:
    w1 = asyncio.run(work_repo.create(Work(
        work_key="k525", composer="Wolfgang Amadeus Mozart", title="Eine kleine Nachtmusik",
        catalogue="K. 525", musical_key="G major", opus="KV 525", duration="17:00",
        measures=0, pages=12, parts=4, complexity=3, license="Public Domain",
        public_domain=True, description="Serenata en sol mayor.",
        thumbnails='["https://t.example/1.png"]',
        tags="classical,serenade",
    )))
    asyncio.run(work_repo.replace_tags(w1.id, ["classical", "serenade"]))
    asyncio.run(work_repo.replace_genres(w1.id, ["Classical"]))
    asyncio.run(work_repo.replace_instruments(w1.id, ["Violin", "Viola", "Cello"]))
    asyncio.run(work_repo.replace_parts(w1.id, ["Violin I", "Violin II"]))
    asyncio.run(entry_repo.create(ArchiveEntry(
        archive_id=1, relative_path="mxl/1/30/eine.mxl", logical_id="30/1",
        composer=w1.composer, title=w1.title, work_id=w1.id, file_id=10,
        status=ArchiveEntryStatus.READY,
    )))
    asyncio.run(entry_repo.create(ArchiveEntry(
        archive_id=1, relative_path="pdf/1/30/eine.pdf", logical_id="30/1",
        composer=w1.composer, title=w1.title, work_id=w1.id, file_id=11,
        status=ArchiveEntryStatus.READY,
    )))
    asyncio.run(work_repo.create(Work(
        work_key="k626", composer="Wolfgang Amadeus Mozart", title="Requiem", catalogue="K. 626",
    )))


def _app(container: Container) -> FastAPI:
    app = FastAPI()
    app.state.container = container
    errors.register_exception_handlers(app)
    app.include_router(provider_routes.router)
    return app


@pytest.fixture
def client(tmp_path):
    settings = _settings(tmp_path)
    work_repo = InMemoryWorkRepository()
    entry_repo = InMemoryArchiveEntryRepository()
    composer_repo = InMemoryComposerRepository()
    _seed(work_repo, entry_repo)
    _seed_composer(composer_repo)
    return TestClient(_app(_build_container(settings, work_repo, entry_repo, composer_repo)))


def test_version(client):
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"contract", "version"}


def test_lookup_is_minimal(client):
    resp = client.get("/api/lookup?q=mozart")
    assert resp.status_code == 200
    body = resp.json()
    assert "works" in body
    assert len(body["works"]) == 2
    item = body["works"][0]
    assert set(item.keys()) == {"id", "title", "composer", "catalogue", "confidence"}
    assert "metadata" not in item
    assert "resources" not in item
    assert "statistics" not in item


def test_search_returns_complete_works(client):
    resp = client.get("/api/search?q=mozart")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["works"]) == 2
    w = next(w for w in body["works"] if w["id"] == 1)
    expected_keys = {"id", "title", "composer", "composer_id", "catalogue", "aliases",
                     "metadata", "statistics", "resources"}
    assert set(w.keys()) == expected_keys
    assert w["composer"] == "Wolfgang Amadeus Mozart"
    assert w["composer_id"] == "8f5b3a7e"
    md = w["metadata"]
    for key in ("subtitle", "artist", "song_name", "opus", "musical_key", "duration", "measures",
                "pages", "parts", "complexity", "license", "public_domain", "description",
                "thumbnails", "genres", "tags", "instruments", "parts_names"):
        assert key in md
    assert w["metadata"]["genres"] == ["Classical"]
    assert w["metadata"]["tags"] == ["classical", "serenade"]
    assert w["metadata"]["instruments"] == ["Violin", "Viola", "Cello"]
    assert w["statistics"] == {"favorites": None, "downloads": None, "views": None, "rating": None}
    resources = w["resources"]
    assert len(resources) == 2
    for r in resources:
        assert set(r.keys()) == {"id", "format", "mime_type", "available", "license", "links"}
        assert set(r["links"].keys()) == {"download", "view", "thumbnail"}
        assert r["available"] is True
        assert r["links"]["download"] == f"/api/download/{r['id']}"


def test_search_responses_contain_no_osap_concepts(client):
    body = client.get("/api/search?q=mozart").json()
    text = str(body).lower()
    for banned in ("representation", "matching", "resolution", "relationship", "knowledge", "work_resolution"):
        assert banned not in text


def test_resource_reuses_search_dto(client):
    search_body = client.get("/api/search?q=mozart").json()
    search_work = next(w for w in search_body["works"] if w["id"] == 1)
    resource_body = client.get("/api/resource/1").json()
    assert resource_body == {"work": search_work}


def test_download_redirects_without_internal_paths(client):
    resp = client.get("/api/download/10", follow_redirects=False)
    assert resp.status_code in (301, 302, 307)
    location = resp.headers["location"]
    assert "content" in location
    assert ".mxl" not in location
    assert "mxl/1/30" not in location
    assert location.startswith("http://storage.example/")


def test_search_has_no_n_plus_one(tmp_path):
    class CountingEntries(InMemoryArchiveEntryRepository):
        def __init__(self):
            super().__init__()
            self.bulk_calls = 0

        async def list_by_work_ids(self, work_ids):
            self.bulk_calls += 1
            return await super().list_by_work_ids(work_ids)

    class CountingWorks(InMemoryWorkRepository):
        def __init__(self):
            super().__init__()
            self.bulk_calls = 0

        async def get_lists_bulk(self, work_ids):
            self.bulk_calls += 1
            return await super().get_lists_bulk(work_ids)

    settings = _settings(tmp_path)
    work_repo = CountingWorks()
    entry_repo = CountingEntries()
    _seed(work_repo, entry_repo)
    client = TestClient(_app(_build_container(settings, work_repo, entry_repo)))

    resp = client.get("/api/search?q=mozart")
    assert resp.status_code == 200
    assert len(resp.json()["works"]) == 2
    assert entry_repo.bulk_calls == 1
    assert work_repo.bulk_calls == 1
