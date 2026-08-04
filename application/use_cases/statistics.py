from __future__ import annotations

from datetime import UTC, datetime

from domain.entities.archive_entry import ArchiveEntryStatus
from domain.entities.statistics import Statistics
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository
from domain.ports.repositories import FileRepository
from domain.ports.statistics_repository import StatisticsRepository


class RefreshStatistics:
    """Recomputa una instantánea de estadísticas del repositorio."""

    def __init__(
        self,
        archives: ArchiveRepository,
        entries: ArchiveEntryRepository,
        files: FileRepository,
        statistics: StatisticsRepository,
    ) -> None:
        self._archives = archives
        self._entries = entries
        self._files = files
        self._statistics = statistics

    async def execute(self) -> Statistics:
        stats = Statistics(
            archives=await self._archives.count(),
            entries=await self._entries.count_total(),
            files=await self._files.count(),
            downloaded_tar=await self._archives.count_downloaded(),
            materialized=await self._entries.count_by_status(ArchiveEntryStatus.READY),
            pending=await self._entries.count_by_status(ArchiveEntryStatus.MISSING),
            bytes=await self._files.sum_size(),
            computed_at=datetime.now(UTC),
        )
        return await self._statistics.save(stats)


class GetStatistics:
    """Devuelve las últimas estadísticas; las recalcula si aún no existen."""

    def __init__(
        self,
        refresh: RefreshStatistics,
        statistics: StatisticsRepository,
    ) -> None:
        self._refresh = refresh
        self._statistics = statistics

    async def execute(self, *, refresh: bool = False) -> Statistics:
        if refresh:
            return await self._refresh.execute()
        latest = await self._statistics.get_latest()
        if latest is not None:
            return latest
        return await self._refresh.execute()
