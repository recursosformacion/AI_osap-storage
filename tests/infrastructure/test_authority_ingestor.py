"""Ingestor JSON → authority_identifiers: validación, upsert e idempotencia."""

from __future__ import annotations

import asyncio

from infrastructure.services.authority_ingestor import AuthoritySnapshotIngestor
from tests.fakes import InMemoryAuthorityIdentifierRepository


def test_roundtrip_list_for_entity_returns_same_identifiers() -> None:
    async def run():
        repo = InMemoryAuthorityIdentifierRepository()
        ingestor = AuthoritySnapshotIngestor(repo)
        result = await ingestor.ingest_composers(
            {"wa mozart": {"canonical_name": "Wolfgang Amadeus Mozart", "isni": "0000000121269154", "wikidata": "Q254"}}
        )
        assert result.inserted == 2
        ids = await repo.list_for_entity("composer", "wa mozart")
        assert len(ids) == 2
        assert {i.scheme: i.value for i in ids} == {"isni": "0000000121269154", "wikidata": "Q254"}

    asyncio.run(run())


def test_idempotent_second_run_is_all_ignored() -> None:
    async def run():
        repo = InMemoryAuthorityIdentifierRepository()
        ingestor = AuthoritySnapshotIngestor(repo)
        composers = {"wa mozart": {"isni": "0000000121269154"}}
        await ingestor.ingest_composers(composers)
        before = len(await repo.list_for_entity("composer", "wa mozart"))
        result = await ingestor.ingest_composers(composers)
        assert result.inserted == 0
        assert result.updated == 0
        assert result.ignored == 1
        assert len(await repo.list_for_entity("composer", "wa mozart")) == before == 1  # no 2N

    asyncio.run(run())


def test_updated_when_value_changes() -> None:
    async def run():
        repo = InMemoryAuthorityIdentifierRepository()
        ingestor = AuthoritySnapshotIngestor(repo)
        await ingestor.ingest_composers({"wa mozart": {"isni": "A"}})
        result = await ingestor.ingest_composers({"wa mozart": {"isni": "B"}})
        assert result.updated == 1
        ids = await repo.list_for_entity("composer", "wa mozart")
        assert len(ids) == 1  # no duplica fila
        assert ids[0].value == "B"

    asyncio.run(run())


def test_invalid_empty_entity_id_is_rejected() -> None:
    async def run():
        repo = InMemoryAuthorityIdentifierRepository()
        ingestor = AuthoritySnapshotIngestor(repo)
        result = await ingestor.ingest_composers({"": {"isni": "X"}})
        assert result.invalid == 1
        assert result.inserted == 0
        assert await repo.list_for_entity("composer", "") == []

    asyncio.run(run())


def test_same_identifier_two_entities_reports_conflict_but_ingests() -> None:
    async def run():
        repo = InMemoryAuthorityIdentifierRepository()
        ingestor = AuthoritySnapshotIngestor(repo)
        result = await ingestor.ingest_composers(
            {"a": {"isni": "0000000121269154"}, "b": {"isni": "0000000121269154"}}
        )
        # No se impone unicidad de scheme+value: ambos se ingieren, pero se reporta conflicto.
        assert result.conflict == 1
        assert result.inserted == 2
        assert len(await repo.list_for_entity("composer", "a")) == 1
        assert len(await repo.list_for_entity("composer", "b")) == 1

    asyncio.run(run())
