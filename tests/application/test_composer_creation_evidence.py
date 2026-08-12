from __future__ import annotations

import asyncio

from application.use_cases.composer_admin import GetComposerDetail, MergeComposers
from application.use_cases.populate_composers import PopulateComposers
from domain.entities.composer import Composer
from tests.fakes import InMemoryComposerRepository


def _repo() -> InMemoryComposerRepository:
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="target", name="Johann Sebastian Bach")))
    asyncio.run(repo.create(Composer(id="source", name="J. S. Bach")))
    return repo


def test_record_creation_evidence():
    repo = _repo()
    ev = asyncio.run(repo.add_creation_evidence(
        "target",
        work_id=264,
        work_title="Preludio en Do mayor",
        extracted_author="J. S. Bach",
        provider="IMSLP",
        resource_reference="ref/prae/264",
    ))
    assert ev.work_id == 264
    assert ev.extracted_author == "J. S. Bach"
    assert ev.provider == "IMSLP"
    assert ev.resource_reference == "ref/prae/264"
    assert len(asyncio.run(repo.list_creation_evidence("target"))) == 1


def test_detail_includes_creation_evidence():
    repo = _repo()
    asyncio.run(repo.add_creation_evidence(
        "target", work_id=1, work_title="Prelude", extracted_author="Joh. Seb. Bach", provider="X",
    ))
    detail = asyncio.run(GetComposerDetail(repo).execute("target"))
    assert len(detail.creation_evidence) == 1
    assert detail.creation_evidence[0].work_title == "Prelude"
    assert detail.creation_evidence[0].provider == "X"


def test_merge_redirects_evidence_and_never_deletes():
    repo = _repo()
    asyncio.run(repo.add_creation_evidence(
        "source", work_id=10, work_title="BWV 846", extracted_author="Johann Seb. Bach", provider="Y",
    ))
    asyncio.run(MergeComposers(repo).execute("target", ["source"]))

    # La evidencia del source se redirige al target; el source queda sin evidencia propia.
    target_ev = asyncio.run(repo.list_creation_evidence("target"))
    assert len(target_ev) == 1
    assert target_ev[0].composer_id == "target"
    assert target_ev[0].work_title == "BWV 846"
    assert asyncio.run(repo.list_creation_evidence("source")) == []

    # Y el detalle del target la muestra.
    detail = asyncio.run(GetComposerDetail(repo).execute("target"))
    assert len(detail.creation_evidence) == 1
    assert detail.creation_evidence[0].work_title == "BWV 846"


def test_populate_records_evidence_when_provider_given():
    repo = InMemoryComposerRepository()
    asyncio.run(PopulateComposers(repo).execute(
        ["W. A. Mozart", "Wolfgang Amadeus Mozart"], provider="pdmx"
    ))
    composers = repo._composers
    assert len(composers) == 2
    for cid in composers:
        ev = asyncio.run(repo.list_creation_evidence(cid))
        assert len(ev) == 1
        assert ev[0].provider == "pdmx"


def test_backfill_creation_evidence_idempotent():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="a", name="Composer A")))
    asyncio.run(repo.create(Composer(id="b", name="Composer B")))
    repo.set_work(1, "a", "Obra A")
    repo.set_work(2, "b", "Obra B")
    repo.set_work(3, "b", "Otra B")

    # Solo el que no tiene evidencia la recibe (de su menor work_id).
    assert asyncio.run(repo.backfill_creation_evidence(provider="pdmx")) == 2
    ev_a = asyncio.run(repo.list_creation_evidence("a"))
    assert len(ev_a) == 1 and ev_a[0].work_id == 1
    ev_b = asyncio.run(repo.list_creation_evidence("b"))
    assert len(ev_b) == 1 and ev_b[0].work_id == 2  # menor work_id

    # Idempotente: repetir no crea más.
    assert asyncio.run(repo.backfill_creation_evidence(provider="pdmx")) == 0
    assert len(asyncio.run(repo.list_creation_evidence("a"))) == 1


def test_backfill_skips_merged_and_without_works():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="act", name="Activo")))
    asyncio.run(repo.create(Composer(id="mrg", name="Fusionado", status="merged")))
    repo.set_work(1, "act", "Obra")
    asyncio.run(repo.backfill_creation_evidence(provider="pdmx"))
    assert len(asyncio.run(repo.list_creation_evidence("act"))) == 1
    assert len(asyncio.run(repo.list_creation_evidence("mrg"))) == 0


def test_prune_zero_work_composers():
    from application.use_cases.composer_admin import PruneComposers
    from domain.entities.composer import UNKNOWN_COMPOSER_ID

    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="with-works", name="Con Obras")))
    asyncio.run(repo.create(Composer(id="phantom", name="Fantasma")))
    repo.set_work(1, "with-works", "Obra")
    removed = asyncio.run(PruneComposers(repo).execute())
    assert removed == 1
    assert asyncio.run(repo.get_by_id("phantom")) is None
    assert asyncio.run(repo.get_by_id("with-works")) is not None
    # "Compositor sin indicar" no se borra aunque no tenga obras en el fake
    asyncio.run(repo.create(Composer(id=UNKNOWN_COMPOSER_ID, name="Compositor sin indicar")))
    asyncio.run(PruneComposers(repo).execute())
    assert asyncio.run(repo.get_by_id(UNKNOWN_COMPOSER_ID)) is not None
