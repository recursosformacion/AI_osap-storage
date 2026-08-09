from __future__ import annotations

from typing import Protocol

from domain.entities.voting import ComposerStatistics, StatisticsRun, Vote, WorkStatistics


class VotingRepository(Protocol):
    """Persistencia de votos (fuente) y estadísticas derivadas (Work / Composer).

    La unicidad "un usuario una vez al día por obra" se garantiza mediante una
    restricción UNIQUE en la base de datos, no solo en Python, de forma segura
    ante peticiones concurrentes.
    """

    async def add_vote(self, user_id: str, work_id: int, vote: int) -> Vote:
        """Registra un voto (vote_day en UTC). Lanza DuplicateVote si ya votó hoy."""

    async def get_work_statistics(self, work_id: int) -> WorkStatistics | None: ...

    async def get_work_statistics_bulk(self, work_ids: list[int]) -> dict[int, WorkStatistics]:
        """Recupera estadísticas de varias obras (sin N+1)."""

    async def get_composer_statistics(self, composer_id: str) -> ComposerStatistics | None: ...

    async def recompute_all(self) -> StatisticsRun:
        """Recalcula todas las estadísticas derivadas. Idempotente. Transaccional."""
