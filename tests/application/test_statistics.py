from __future__ import annotations

from application.use_cases.statistics import GetStatistics, RefreshStatistics
from domain.entities.archive import Archive
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.file import File
from tests.fakes import (
    InMemoryArchiveEntryRepository,
    InMemoryArchiveRepository,
    InMemoryFileRepository,
    InMemoryStatisticsRepository,
)

SHA = "a" * 64


async def test_refresh_statistics_counts_repository():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    files = InMemoryFileRepository()
    stats = InMemoryStatisticsRepository()

    await archives.create(Archive(name="a.tar.gz"))
    await archives.create(Archive(name="b.tar.gz", local_path="/x/y.tar.gz"))
    await entries.create(ArchiveEntry(archive_id=1, relative_path="mxl/a.mxl"))
    await entries.create(
        ArchiveEntry(archive_id=1, relative_path="mxl/b.mxl", status=ArchiveEntryStatus.READY, file_id=1)
    )
    await files.create(File(sha256=SHA, name="b.mxl", size_bytes=100))

    result = await RefreshStatistics(archives, entries, files, stats).execute()

    assert result.archives == 2
    assert result.entries == 2
    assert result.files == 1
    assert result.downloaded_tar == 1
    assert result.materialized == 1
    assert result.pending == 1
    assert result.bytes == 100


async def test_get_statistics_recomputes_when_empty():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    files = InMemoryFileRepository()
    stats = InMemoryStatisticsRepository()
    refresh = RefreshStatistics(archives, entries, files, stats)

    result = await GetStatistics(refresh, stats).execute()

    assert result.archives == 0
    assert result.entries == 0
    assert result.files == 0
