from __future__ import annotations

from typing import Protocol

from domain.entities.statistics import Statistics


class StatisticsRepository(Protocol):
    async def get_latest(self) -> Statistics | None: ...

    async def save(self, stats: Statistics) -> Statistics: ...
