from __future__ import annotations

import asyncio
import json

from application.use_cases.musicbrainz_enrich import EnrichComposersMusicBrainz
from domain.entities.composer import Composer
from infrastructure.services.musicbrainz_client import CachedMusicBrainzClient
from tests.fakes import InMemoryComposerRepository, InMemoryMusicBrainzCacheRepository


class FakeMusicBrainz:
    def __init__(self, artists_by_query: dict[str, list[dict]]) -> None:
        self._data = artists_by_query
        self.calls = []

    async def search_artists(self, name: str) -> list[dict]:
        self.calls.append(name)
        return self._data.get(name, [])


def _person(name: str, mbid: str, aliases=None) -> dict:
    return {"id": mbid, "name": name, "type": "Person", "score": 100,
            "aliases": aliases or []}


def test_renames_and_marks_correct():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="c", name="W A Mozart")))
    mb = FakeMusicBrainz({"W A Mozart": [_person("Wolfgang Amadeus Mozart", "mbid-1")]})
    counts = asyncio.run(EnrichComposersMusicBrainz(repo, mb).execute(limit=10))
    assert counts["renamed"] == 1
    comp = asyncio.run(repo.get_by_id("c"))
    assert comp.name == "Wolfgang Amadeus Mozart"
    assert comp.musicbrainz_id == "mbid-1"
    assert comp.review_status == "correct"


def test_merges_into_existing_canonical_and_reassigns_works():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="canon", name="Wolfgang Amadeus Mozart")))
    asyncio.run(repo.create(Composer(id="variant", name="W A Mozart")))
    repo.set_work(1, "variant", "Sonata de la variante")
    mb = FakeMusicBrainz({"W A Mozart": [_person("Wolfgang Amadeus Mozart", "mbid-1")]})
    counts = asyncio.run(EnrichComposersMusicBrainz(repo, mb).execute(limit=10))
    assert counts["merged"] == 1
    # La variante queda merged; el canónico recibe el MBID y queda correct.
    assert asyncio.run(repo.get_by_id("variant")).status == "merged"
    canon = asyncio.run(repo.get_by_id("canon"))
    assert canon.status == "active"
    assert canon.musicbrainz_id == "mbid-1"
    assert canon.review_status == "correct"
    # Las obras de la variante se reasignan al canónico.
    detail = asyncio.run(repo.get_detail("canon"))
    assert detail.works_count == 1


def test_no_match_leaves_not_reviewed():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="c", name="Compositor Raro Xyz")))
    mb = FakeMusicBrainz({"Compositor Raro Xyz": []})
    counts = asyncio.run(EnrichComposersMusicBrainz(repo, mb).execute(limit=10))
    assert counts["no_match"] == 1
    comp = asyncio.run(repo.get_by_id("c"))
    assert comp.name == "Compositor Raro Xyz"
    assert comp.review_status == "not_reviewed"


def test_only_person_type_accepted():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="c", name="2Cellos")))
    mb = FakeMusicBrainz({"2Cellos": [{"id": "g1", "name": "2Cellos", "type": "Group", "score": 99}]})
    counts = asyncio.run(EnrichComposersMusicBrainz(repo, mb).execute(limit=10))
    assert counts["no_match"] == 1


def test_cache_avoids_second_api_call():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="c", name="W A Mozart")))
    cache = InMemoryMusicBrainzCacheRepository()
    # Pre-carga la caché: la segunda ejecución NO debe llamar al API.
    artists = [_person("Wolfgang Amadeus Mozart", "mbid-1")]
    asyncio.run(cache.set("W A Mozart", json.dumps(artists)))
    mb = FakeMusicBrainz({})
    cached = CachedMusicBrainzClient(mb, cache)
    counts = asyncio.run(EnrichComposersMusicBrainz(repo, cached).execute(limit=10))
    assert counts["renamed"] == 1
    assert mb.calls == []  # no se llamó al API (usó caché)


def test_cached_client_populates_cache_on_miss():
    cache = InMemoryMusicBrainzCacheRepository()
    mb = FakeMusicBrainz({"Mozart": [_person("Wolfgang Amadeus Mozart", "mbid-9")]})
    cached = CachedMusicBrainzClient(mb, cache)
    asyncio.run(cached.search_artists("Mozart"))
    assert "Mozart" in cache._items
    assert mb.calls == ["Mozart"]
