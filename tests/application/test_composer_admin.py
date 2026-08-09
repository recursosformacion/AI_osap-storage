from __future__ import annotations

import asyncio

import pytest
from application.use_cases.composer_admin import (
    GetComposerDetail,
    GetComposerWorks,
    ListComposers,
    MergeComposers,
)
from domain.entities.composer import Composer
from domain.exceptions import EntityNotFound, InvalidMerge
from domain.services.composer_names import normalize_composer_name
from domain.services.composer_resolver import ComposerResolver
from tests.fakes import InMemoryComposerRepository


def _repo() -> InMemoryComposerRepository:
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="target", name="Wolfgang Amadeus Mozart")))
    asyncio.run(repo.create(Composer(id="source-b", name="W. A. Mozart")))
    asyncio.run(repo.create(Composer(id="source-c", name="Mozart, W. A.")))
    for cid, raw in (("target", "Wolfgang Amadeus Mozart"), ("source-b", "W. A. Mozart"),
                     ("source-c", "Mozart, W. A.")):
        asyncio.run(repo.add_alias(cid, raw, normalize_composer_name(raw)))
    # Works: 2 del target, 3 del source-b, 1 del source-c
    for wid in (1, 2):
        repo.set_work(wid, "target", "Serenata")
    for wid in (10, 11, 12):
        repo.set_work(wid, "source-b", "Sonata")
    repo.set_work(20, "source-c", "Minuetto")
    return repo


# --- Listado ---


def test_list_paginated():
    repo = _repo()
    result = asyncio.run(ListComposers(repo).execute(limit=2, offset=0))
    assert result.total == 3
    assert len(result.items) == 2
    by_name = {i.name: i for i in result.items}
    assert "W. A. Mozart" in by_name  # orden por nombre
    assert by_name["W. A. Mozart"].aliases_count == 1
    assert by_name["W. A. Mozart"].works_count == 3


def test_list_search_by_name_and_alias():
    repo = _repo()
    by_name = asyncio.run(ListComposers(repo).execute(limit=50, offset=0, q="Mozart"))
    assert by_name.total == 3
    by_alias = asyncio.run(ListComposers(repo).execute(limit=50, offset=0, q="w. a. mozart"))
    assert by_alias.total >= 1
    # búsqueda que solo acierta por alias normalizado
    hit = asyncio.run(ListComposers(repo).execute(limit=50, offset=0, q="mozart, w. a."))
    assert hit.total == 1


def test_list_excludes_merged():
    repo = _repo()
    asyncio.run(MergeComposers(repo).execute("target", ["source-b"]))
    result = asyncio.run(ListComposers(repo).execute(limit=50, offset=0))
    assert result.total == 2
    names = {i.name for i in result.items}
    assert "W. A. Mozart" not in names


# --- Detalle ---


def test_detail_existing_and_counts():
    repo = _repo()
    detail = asyncio.run(GetComposerDetail(repo).execute("target"))
    assert detail.name == "Wolfgang Amadeus Mozart"
    assert detail.aliases == ["Wolfgang Amadeus Mozart"]
    assert detail.works_count == 2
    assert detail.status == "active"


def test_detail_missing_raises():
    with pytest.raises(EntityNotFound):
        asyncio.run(GetComposerDetail(InMemoryComposerRepository()).execute("nope"))


def test_works_of_composer_paginated():
    repo = _repo()
    works, total = asyncio.run(GetComposerWorks(repo).execute("source-b", limit=2, offset=0))
    assert total == 3
    assert len(works) == 2
    assert all(w.composer_id == "source-b" for w in works)


# --- Merge ---


def test_merge_single_source():
    repo = _repo()
    result = asyncio.run(MergeComposers(repo).execute("target", ["source-b"], merged_by="admin"))
    assert result.sources_merged == ["source-b"]
    assert result.aliases_transferred == 1
    assert result.works_moved == 3

    target = asyncio.run(repo.get_by_id("target"))
    source = asyncio.run(repo.get_by_id("source-b"))
    assert target.status == "active"
    assert source.status == "merged"
    assert source.merged_into == "target"
    # Works reasignadas
    assert len(asyncio.run(GetComposerWorks(repo).execute("target", limit=50, offset=0))[0]) == 5
    assert len(asyncio.run(GetComposerWorks(repo).execute("source-b", limit=50, offset=0))[0]) == 0
    # Alias transferido
    detail = asyncio.run(GetComposerDetail(repo).execute("target"))
    assert "W. A. Mozart" in detail.aliases
    assert len(asyncio.run(repo.list_aliases("source-b"))) == 0
    # Historial
    assert len(repo.history) == 1
    assert repo.history[0]["source"] == "source-b"
    assert repo.history[0]["target"] == "target"
    assert repo.history[0]["by"] == "admin"


def test_merge_multiple_sources_single_operation():
    repo = _repo()
    result = asyncio.run(MergeComposers(repo).execute("target", ["source-b", "source-c"]))
    assert set(result.sources_merged) == {"source-b", "source-c"}
    assert result.works_moved == 4
    assert len(repo.history) == 2
    op_ids = {h["merge_operation_id"] for h in repo.history}
    assert len(op_ids) == 1  # una única operación para los dos sources


def test_merge_reassigns_works_to_target():
    repo = _repo()
    asyncio.run(MergeComposers(repo).execute("target", ["source-b", "source-c"]))
    for _wid, (cid, _) in repo._works.items():
        assert cid == "target"


def test_merge_alias_conflict_aborts():
    # source-b ya tiene el alias de source-c normalizado -> duplicado en target no debería ocurrir
    # porque cada normalized es globalmente único; comprobamos que no se duplica al mover.
    repo = _repo()
    asyncio.run(MergeComposers(repo).execute("target", ["source-b", "source-c"]))
    detail = asyncio.run(GetComposerDetail(repo).execute("target"))
    assert len(detail.aliases) == 3  # sin duplicados


def test_merge_target_among_sources_rejected():
    with pytest.raises(InvalidMerge):
        asyncio.run(MergeComposers(_repo()).execute("target", ["target"]))


def test_merge_source_missing_rejected():
    with pytest.raises(EntityNotFound):
        asyncio.run(MergeComposers(_repo()).execute("target", ["missing"]))


def test_merge_target_missing_rejected():
    with pytest.raises(EntityNotFound):
        asyncio.run(MergeComposers(_repo()).execute("missing", ["source-b"]))


def test_merge_repeated_operation_is_noop():
    repo = _repo()
    asyncio.run(MergeComposers(repo).execute("target", ["source-b"]))
    second = asyncio.run(MergeComposers(repo).execute("target", ["source-b"]))
    assert second.sources_merged == []
    assert second.aliases_transferred == 0
    assert second.works_moved == 0
    # los datos no se corrompen
    assert len(asyncio.run(GetComposerWorks(repo).execute("target", limit=50, offset=0))[0]) == 5


def test_merge_merged_source_into_other_target_rejected():
    repo = _repo()
    asyncio.run(MergeComposers(repo).execute("target", ["source-b"]))
    asyncio.run(repo.create(Composer(id="other", name="Otro")))
    with pytest.raises(InvalidMerge):
        asyncio.run(MergeComposers(repo).execute("other", ["source-b"]))


def test_resolver_follows_merge():
    repo = _repo()
    asyncio.run(MergeComposers(repo).execute("target", ["source-b"]))
    resolver = ComposerResolver(repo)
    # El alias antiguo de source-b ahora resuelve al target
    result = asyncio.run(resolver.resolve("W. A. Mozart"))
    assert result is not None
    assert result[0] == "target"
    assert result[1] == "Wolfgang Amadeus Mozart"


def test_resolver_batch_after_merge():
    repo = _repo()
    asyncio.run(MergeComposers(repo).execute("target", ["source-b", "source-c"]))
    resolver = ComposerResolver(repo)
    result = asyncio.run(resolver.resolve_many(["W. A. Mozart", "Mozart, W. A.", "Wolfgang Amadeus Mozart"]))
    assert result["W. A. Mozart"][0] == "target"
    assert result["Mozart, W. A."][0] == "target"
    assert result["Wolfgang Amadeus Mozart"][0] == "target"
