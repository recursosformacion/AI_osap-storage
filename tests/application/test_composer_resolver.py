from __future__ import annotations

import asyncio

import pytest
from domain.entities.composer import Composer
from domain.exceptions import DuplicateComposerAlias
from domain.services.composer_names import normalize_composer_name
from domain.services.composer_resolver import ComposerResolver
from tests.fakes import InMemoryComposerRepository


def _seed() -> tuple[InMemoryComposerRepository, str]:
    repo = InMemoryComposerRepository()
    composer = asyncio.run(repo.create(Composer(id="8f5b3a7e", name="Wolfgang Amadeus Mozart")))
    for alias in ("Mozart", "Mozart, W. A.", "W. A. Mozart", "Wolfgang Amadeus Mozart"):
        asyncio.run(repo.add_alias(composer.id, alias, normalize_composer_name(alias)))
    return repo, composer.id


def test_alias_exact_resolves():
    repo, cid = _seed()
    resolver = ComposerResolver(repo)
    result = asyncio.run(resolver.resolve("Mozart"))
    assert result == (cid, "Wolfgang Amadeus Mozart")


def test_alternative_alias_resolves():
    repo, cid = _seed()
    resolver = ComposerResolver(repo)
    assert asyncio.run(resolver.resolve("W. A. Mozart")) == (cid, "Wolfgang Amadeus Mozart")


def test_trivial_differences_resolve():
    repo, cid = _seed()
    resolver = ComposerResolver(repo)
    assert asyncio.run(resolver.resolve("w. a. mozart")) == (cid, "Wolfgang Amadeus Mozart")


def test_unknown_composer_returns_none():
    repo, _ = _seed()
    resolver = ComposerResolver(repo)
    assert asyncio.run(resolver.resolve("Compositor inexistente")) is None
    assert asyncio.run(resolver.resolve(None)) is None


def test_resolve_many_batch_and_no_n_plus_one():
    repo, cid = _seed()
    calls = []

    class CountingRepo(InMemoryComposerRepository):
        async def resolve_many_by_normalized(self, normalized):
            calls.append(len(normalized))
            return await super().resolve_many_by_normalized(normalized)

    seeded, seeded_cid = _seed()
    counting = CountingRepo()
    counting._composers = seeded._composers
    counting._aliases = seeded._aliases
    counting._by_normalized = seeded._by_normalized
    counting._seq = seeded._seq
    resolver = ComposerResolver(counting)
    names = ["Mozart", "W. A. Mozart", "w. a. mozart", "Compositor inexistente", "Mozart"]
    result = asyncio.run(resolver.resolve_many(names))
    assert result["Mozart"] == (cid, "Wolfgang Amadeus Mozart")
    assert result["W. A. Mozart"] == (cid, "Wolfgang Amadeus Mozart")
    assert result["w. a. mozart"] == (cid, "Wolfgang Amadeus Mozart")
    assert result["Compositor inexistente"] is None
    assert len(calls) == 1  # una sola consulta por lotes, nunca N consultas


def test_duplicate_normalized_alias_rejected():
    repo, cid = _seed()
    other = asyncio.run(repo.create(Composer(id="another", name="Alguien")))
    with pytest.raises(DuplicateComposerAlias):
        asyncio.run(repo.add_alias(other.id, "W. A. Mozart", normalize_composer_name("W. A. Mozart")))
