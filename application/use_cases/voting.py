from __future__ import annotations

from domain.entities.composer import ComposerStatus
from domain.entities.voting import ComposerStatistics, StatisticsRun, Vote, WorkStatistics
from domain.exceptions import EntityNotFound
from domain.ports.composer_repository import ComposerRepository
from domain.ports.voting_repository import VotingRepository
from domain.ports.work_repository import WorkRepository


class RecordVote:
    """Registra el voto de un usuario sobre una obra (una vez al día)."""

    def __init__(
        self, votes: VotingRepository, works: WorkRepository
    ) -> None:
        self._votes = votes
        self._works = works

    async def execute(self, user_id: str, work_id: int, vote: int) -> Vote:
        if await self._works.get_by_id(work_id) is None:
            raise EntityNotFound("work", work_id)
        return await self._votes.add_vote(user_id, work_id, vote)


class GetWorkStatistics:
    """Devuelve las estadísticas derivadas de una obra (o ceros si no hay votos)."""

    def __init__(self, votes: VotingRepository, works: WorkRepository) -> None:
        self._votes = votes
        self._works = works

    async def execute(self, work_id: int) -> WorkStatistics:
        if await self._works.get_by_id(work_id) is None:
            raise EntityNotFound("work", work_id)
        stats = await self._votes.get_work_statistics(work_id)
        if stats is None:
            return WorkStatistics(work_id=work_id, vote_count=0, work_count=1)
        return stats


class GetComposerStatistics:
    """Devuelve la valoración agregada del compositor canónico.

    Si el id corresponde a un compositor fusionado, resuelve al target activo.
    """

    def __init__(
        self, votes: VotingRepository, composers: ComposerRepository
    ) -> None:
        self._votes = votes
        self._composers = composers

    async def execute(self, composer_id: str) -> ComposerStatistics:
        canonical = await self._resolve_canonical(composer_id)
        stats = await self._votes.get_composer_statistics(canonical)
        if stats is None:
            return ComposerStatistics(composer_id=canonical, vote_count=0, work_count=0)
        return stats

    async def _resolve_canonical(self, composer_id: str) -> str:
        composer = await self._composers.get_by_id(composer_id)
        if composer is None:
            raise EntityNotFound("composer", composer_id)
        seen: set[str] = set()
        while composer.status == ComposerStatus.MERGED and composer.merged_into:
            if composer.id in seen:
                break
            seen.add(composer.id)
            nxt = await self._composers.get_by_id(composer.merged_into)
            if nxt is None:
                break
            composer = nxt
        return composer.id


class RefreshVotingStatistics:
    """Recalcula todas las estadísticas derivadas (votación). Idempotente."""

    def __init__(self, votes: VotingRepository) -> None:
        self._votes = votes

    async def execute(self) -> StatisticsRun:
        return await self._votes.recompute_all()
