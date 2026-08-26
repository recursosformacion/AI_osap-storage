from __future__ import annotations

import asyncio

import pytest
from api.routes import voting as voting_routes
from application.use_cases.voting import (
    GetComposerStatistics,
    GetWorkStatistics,
    RecordVote,
    RefreshVotingStatistics,
)
from domain.entities.composer import Composer
from domain.entities.work import Work
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
    InMemoryVotingRepository,
    InMemoryWorkRepository,
    SyncScheduler,
)

from api import errors


def _settings(tmp_path) -> Settings:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "db:\n  host: 127.0.0.1\n  port: 3306\n  user: dev\n  password: devpass\n"
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


def _container(settings, works, votes, composers) -> Container:
    return Container(
        settings=settings,
        db=object(),  # type: ignore[arg-type]
        file_repo=InMemoryFileRepository(),
        provider_repo=InMemoryProviderRepository(),
        location_repo=InMemoryLocationRepository(),
        job_repo=InMemoryJobRepository(),
        archive_repo=InMemoryArchiveRepository(),
        archive_entry_repo=InMemoryArchiveEntryRepository(),
        work_repo=works,
        composer_repo=composers,
        composer_resolver=object(),  # type: ignore[arg-type]
        voting_repo=votes,
        catalogue_repo=object(),  # type: ignore[arg-type]
        catalogue_queries=object(),  # type: ignore[arg-type]
        table_crud=object(),  # type: ignore[arg-type]
        list_composers=object(),  # type: ignore[arg-type]
        get_composer_detail=object(),  # type: ignore[arg-type]
        get_composer_works=object(),  # type: ignore[arg-type]
        merge_composers=object(),  # type: ignore[arg-type]
        review_composer=object(),  # type: ignore[arg-type]
        classify_composers=object(),  # type: ignore[arg-type]
        clean_composer_names=object(),  # type: ignore[arg-type]
        prune_composers=object(),  # type: ignore[arg-type]
        create_composer=object(),  # type: ignore[arg-type]
        add_alias=object(),  # type: ignore[arg-type]
        list_aliases=object(),  # type: ignore[arg-type]
        move_alias=object(),  # type: ignore[arg-type]
        promote_alias=object(),  # type: ignore[arg-type]
        set_attribution=object(),  # type: ignore[arg-type]
        update_composer=object(),  # type: ignore[arg-type]
        get_composer_biography=object(),  # type: ignore[arg-type]
        update_composer_biography=object(),  # type: ignore[arg-type]
        delete_composer_identifier=object(),  # type: ignore[arg-type]
        list_works_admin=object(),  # type: ignore[arg-type]
        get_work_admin=object(),  # type: ignore[arg-type]
        update_work_admin=object(),  # type: ignore[arg-type]
        composer_review_stats=object(),  # type: ignore[arg-type]
        record_vote=RecordVote(votes, works),
        get_work_statistics=GetWorkStatistics(votes, works),
        get_composer_statistics=GetComposerStatistics(votes, composers),
        refresh_voting_statistics=RefreshVotingStatistics(votes),
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


def _setup():
    works = InMemoryWorkRepository()
    asyncio.run(works.create(Work(id=1, title="w1", work_key="k1")))
    asyncio.run(works.create(Work(id=2, title="w2", work_key="k2")))
    votes = InMemoryVotingRepository()
    votes.set_work(1, "moz")
    votes.set_work(2, "moz")
    composers = InMemoryComposerRepository()
    asyncio.run(composers.create(Composer(id="moz", name="Mozart")))
    return works, votes, composers


@pytest.fixture
def client(tmp_path):
    works, votes, composers = _setup()
    return TestClient(_app(_container(_settings(tmp_path), works, votes, composers)))


def _app(container) -> FastAPI:
    app = FastAPI()
    app.state.container = container
    errors.register_exception_handlers(app)
    app.include_router(voting_routes.router)
    return app


def test_register_vote(client):
    resp = client.post("/api/v1/works/1/votes", json={"user_id": "u1", "vote": 5})
    assert resp.status_code == 201
    body = resp.json()
    assert body["work_id"] == 1
    assert body["vote"] == 5
    assert body["user_id"] == "u1"


def test_duplicate_vote_conflict(client):
    assert client.post("/api/v1/works/1/votes", json={"user_id": "u1", "vote": 4}).status_code == 201
    resp = client.post("/api/v1/works/1/votes", json={"user_id": "u1", "vote": 5})
    assert resp.status_code == 409


def test_vote_out_of_range(client):
    resp = client.post("/api/v1/works/1/votes", json={"user_id": "u1", "vote": 6})
    assert resp.status_code == 422


def test_vote_missing_work_404(client):
    resp = client.post("/api/v1/works/999/votes", json={"user_id": "u1", "vote": 3})
    assert resp.status_code == 404


def test_work_statistics_endpoint(client):
    client.post("/api/v1/works/1/votes", json={"user_id": "u1", "vote": 4})
    client.post("/api/v1/works/1/votes", json={"user_id": "u2", "vote": 5})
    client.post("/api/v1/works/1/votes", json={"user_id": "u3", "vote": 5})
    asyncio.run(RefreshVotingStatistics(_votes(client)).execute())
    resp = client.get("/api/v1/works/1/statistics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["vote_count"] == 3
    assert body["rating"] == pytest.approx(14 / 3)
    assert set(body.keys()) == {"work_id", "rating", "adjusted_rating", "vote_count",
                                "work_count", "confidence", "calculated_at"}


def test_composer_statistics_endpoint(client):
    client.post("/api/v1/works/1/votes", json={"user_id": "u1", "vote": 4})
    client.post("/api/v1/works/2/votes", json={"user_id": "u1", "vote": 5})
    asyncio.run(RefreshVotingStatistics(_votes(client)).execute())
    resp = client.get("/api/v1/composers/moz/statistics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["work_count"] == 2
    assert body["vote_count"] == 2
    assert body["rating"] == pytest.approx(4.5)


def _votes(client):
    return client.app.state.container.voting_repo
