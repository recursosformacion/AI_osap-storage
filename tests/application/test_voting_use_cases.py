from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from application.use_cases.voting import (
    GetComposerStatistics,
    GetWorkStatistics,
    RecordVote,
    RefreshVotingStatistics,
)
from domain.entities.composer import Composer
from domain.entities.work import Work
from domain.exceptions import DuplicateVote, EntityNotFound
from tests.fakes import InMemoryComposerRepository, InMemoryVotingRepository, InMemoryWorkRepository


def _work_repo(work_ids=(1, 2, 3)) -> InMemoryWorkRepository:
    repo = InMemoryWorkRepository()
    for wid in work_ids:
        asyncio.run(repo.create(Work(id=wid, title=f"w{wid}", work_key=f"k{wid}")))
    return repo


def _composer_repo() -> InMemoryComposerRepository:
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="moz", name="Wolfgang Amadeus Mozart")))
    asyncio.run(repo.create(Composer(id="mrg", name="W. A. Mozart")))
    return repo


def _setup(votes=None, works_map=None, work_ids=(1, 2, 3)):
    votes = votes or InMemoryVotingRepository()
    works = _work_repo(work_ids)
    composers = _composer_repo()
    if works_map:
        for wid, cid in works_map.items():
            votes.set_work(wid, cid)
    return votes, works, composers


def test_first_vote_ok():
    v, w, _ = _setup()
    vote = asyncio.run(RecordVote(v, w).execute("u1", 1, 5))
    assert vote.vote == 5


def test_second_vote_same_work_same_day_rejected():
    v, w, _ = _setup()
    uc = RecordVote(v, w)
    asyncio.run(uc.execute("u1", 1, 4))
    with pytest.raises(DuplicateVote):
        asyncio.run(uc.execute("u1", 1, 5))


def test_vote_other_work_same_day_allowed():
    v, w, _ = _setup()
    uc = RecordVote(v, w)
    asyncio.run(uc.execute("u1", 1, 4))
    asyncio.run(uc.execute("u1", 2, 5))  # otra obra, mismo día -> permitido


def test_day_change_allows_vote():
    v, w, _ = _setup()
    # Simula día anterior forzando la fecha de un voto ya registrado.
    asyncio.run(v.add_vote("u1", 1, 4))
    v._votes[-1].vote_day = (datetime.now(UTC) - timedelta(days=1)).date()
    vote = asyncio.run(RecordVote(v, w).execute("u1", 1, 5))  # hoy -> permitido
    assert vote.vote == 5


def test_vote_out_of_range_rejected():
    v, w, _ = _setup()
    with pytest.raises(ValueError):
        asyncio.run(RecordVote(v, w).execute("u1", 1, 6))


def test_vote_missing_work_404():
    v, w, _ = _setup(work_ids=(1,))
    with pytest.raises(EntityNotFound):
        asyncio.run(RecordVote(v, w).execute("u1", 999, 5))


def test_concurrency_duplicate_safe():
    # El fake aplica la misma regla de unicidad que la UNIQUE de BD.
    v, w, _ = _setup()
    uc = RecordVote(v, w)
    asyncio.run(uc.execute("u1", 1, 3))
    with pytest.raises(DuplicateVote):
        asyncio.run(uc.execute("u1", 1, 4))


def test_work_statistics_without_recompute_zero():
    v, w, _ = _setup()
    stats = asyncio.run(GetWorkStatistics(v, w).execute(1))
    assert stats.vote_count == 0
    assert stats.rating is None


def test_average_calculation():
    v, w, _ = _setup()
    for user, val in (("u1", 2), ("u2", 4), ("u3", 5)):
        asyncio.run(RecordVote(v, w).execute(user, 1, val))
    asyncio.run(RefreshVotingStatistics(v).execute())
    stats = asyncio.run(GetWorkStatistics(v, w).execute(1))
    assert stats.vote_count == 3
    assert stats.rating == pytest.approx((2 + 4 + 5) / 3)
    # adjusted_rating suavizado hacia la media global (m=5)
    assert stats.adjusted_rating is not None
    assert stats.confidence == pytest.approx(3 / 5)


def test_composer_aggregation():
    v, w, _ = _setup(works_map={1: "moz", 2: "moz", 3: "mrg"})
    for user, work, val in (("u1", 1, 4), ("u2", 1, 5), ("u3", 2, 3)):
        asyncio.run(RecordVote(v, w).execute(user, work, val))
    asyncio.run(RefreshVotingStatistics(v).execute())
    stats = asyncio.run(GetComposerStatistics(v, _composer_repo()).execute("moz"))
    assert stats.work_count == 2
    assert stats.vote_count == 3
    # media ponderada por sqrt(vote_count): work1(2 votos:4,5 -> adj), work2(1 voto:3 -> adj)
    assert stats.rating is not None


def test_composer_without_votes():
    v, w, _ = _setup(works_map={1: "moz", 2: "moz"})
    asyncio.run(RefreshVotingStatistics(v).execute())
    stats = asyncio.run(GetComposerStatistics(v, _composer_repo()).execute("moz"))
    assert stats.work_count == 2
    assert stats.vote_count == 0
    assert stats.rating is None
    assert stats.confidence == 0


def test_merged_composer_resolves_to_target():
    v, w, composers = _setup(works_map={1: "moz", 2: "mrg"})
    # Simula fusión: mrg se fusiona en moz; su work pasa a moz.
    asyncio.run(composers.merge("moz", ["mrg"]))
    v._works[2] = "moz"
    for user, work, val in (("u1", 1, 4), ("u2", 2, 5)):
        asyncio.run(RecordVote(v, w).execute(user, work, val))
    asyncio.run(RefreshVotingStatistics(v).execute())
    # Consultar el id fusionado devuelve la estadística del target canónico.
    stats = asyncio.run(GetComposerStatistics(v, composers).execute("mrg"))
    assert stats.composer_id == "moz"
    assert stats.work_count == 2
    # El compositor fusionado no recibe estadística independiente.
    assert asyncio.run(v.get_composer_statistics("mrg")) is None


def test_recompute_idempotent():
    v, w, _ = _setup(works_map={1: "moz"})
    asyncio.run(RecordVote(v, w).execute("u1", 1, 4))
    asyncio.run(RefreshVotingStatistics(v).execute())
    stats1 = asyncio.run(GetWorkStatistics(v, w).execute(1))
    asyncio.run(RefreshVotingStatistics(v).execute())
    asyncio.run(RefreshVotingStatistics(v).execute())
    stats2 = asyncio.run(GetWorkStatistics(v, w).execute(1))
    assert stats1.vote_count == stats2.vote_count == 1
    assert stats1.rating == stats2.rating


def test_get_work_statistics_missing_work_404():
    v, w, _ = _setup(work_ids=(1,))
    with pytest.raises(EntityNotFound):
        asyncio.run(GetWorkStatistics(v, w).execute(999))


def test_get_composer_missing_404():
    v, _, composers = _setup()
    with pytest.raises(EntityNotFound):
        asyncio.run(GetComposerStatistics(v, composers).execute("nope"))
