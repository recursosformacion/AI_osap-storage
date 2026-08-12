from __future__ import annotations

import asyncio

import pytest
from application.use_cases.external_works import RegisterExternalWork, external_work_key
from application.use_cases.voting import RecordVote
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from tests.fakes import (
    InMemoryArchiveEntryRepository,
    InMemoryVotingRepository,
    InMemoryWorkRepository,
)


def _register(work_repo, *, reference, provider, composer=None, title=None):
    return asyncio.run(RegisterExternalWork(work_repo).execute(
        reference=reference, provider=provider, composer=composer, title=title,
    ))


def test_15_1_create_external_work_no_local_file():
    works = InMemoryWorkRepository()
    work = _register(works, reference="composer/work/ref-mutopia", provider="Mutopia", title="Sonata")
    assert work.id is not None
    assert work.relative_path == "composer/work/ref-mutopia"  # referencia conservada
    assert work.tags == "Mutopia"  # proveedor en tags
    assert work.work_key == external_work_key("composer/work/ref-mutopia")
    # No hay fichero local: la obra no tiene relative_path de fichero ni archive_entry asociado.


def test_15_2_query_external_work_by_id():
    works = InMemoryWorkRepository()
    created = _register(works, reference="ref/xyz", provider="OpenScore")
    fetched = asyncio.run(works.get_by_id(created.id))
    assert fetched is not None
    assert fetched.relative_path == "ref/xyz"
    assert fetched.tags == "OpenScore"


def test_15_3_vote_external_work_without_file():
    works = InMemoryWorkRepository()
    votes = InMemoryVotingRepository()
    work = _register(works, reference="ref/vote", provider="Mutopia", title="Minuet")
    vote = asyncio.run(RecordVote(votes, works).execute("u1", work.id, 5))
    assert vote.work_id == work.id
    assert vote.vote == 5


def test_15_4_same_reference_no_duplicate():
    works = InMemoryWorkRepository()
    first = _register(works, reference="ref/X", provider="Mutopia")
    second = _register(works, reference="ref/X", provider="Mutopia")
    assert second.id == first.id
    # Solo hay una obra
    assert len(works._items) == 1


def test_15_5_materialization_later_preserves_work_id():
    works = InMemoryWorkRepository()
    work = _register(works, reference="ref/mat", provider="Mutopia")
    work_id = work.id

    # Posteriormente se asocia un fichero local (un archive_entry) a la misma obra.
    entry_repo = InMemoryArchiveEntryRepository()
    asyncio.run(entry_repo.create(ArchiveEntry(
        archive_id=1, relative_path="local/mat.mxl", logical_id="mat", composer="X",
        title="Mat", work_id=work_id, file_id=99, status=ArchiveEntryStatus.READY,
    )))

    # La identidad no cambia.
    still = asyncio.run(works.get_by_id(work_id))
    assert still.id == work_id
    assert still.work_key == work.work_key


def test_15_6_different_provider_same_reference_same_work():
    works = InMemoryWorkRepository()
    a = _register(works, reference="ref/shared", provider="Mutopia")
    b = _register(works, reference="ref/shared", provider="IMSLP")
    # La identidad es por referencia, no por proveedor: no se crea obra nueva.
    assert b.id == a.id
    # Referencias distintas -> obras distintas (no se fusiona por nombre).
    c = _register(works, reference="ref/other", provider="Mutopia")
    assert c.id != a.id


def test_15_7_external_reference_not_used_as_filesystem_path():
    works = InMemoryWorkRepository()
    malicious = "../../../etc/passwd"
    work = _register(works, reference=malicious, provider="Mutopia")
    assert work.relative_path == malicious  # se conserva tal cual
    assert work.work_key == external_work_key(malicious)
    # No se lanza ningún error de acceso a filesystem: el valor solo es metadato.
    fetched = asyncio.run(works.get_by_id(work.id))
    assert fetched.relative_path == malicious


def test_create_with_composer_and_title():
    works = InMemoryWorkRepository()
    work = _register(works, reference="ref/t", provider="OpenScore", composer="Mozart", title="Requiem")
    assert work.composer == "Mozart"
    assert work.title == "Requiem"


def test_empty_reference_rejected():
    works = InMemoryWorkRepository()
    with pytest.raises(ValueError):
        asyncio.run(RegisterExternalWork(works).execute(reference="", provider="Mutopia"))
