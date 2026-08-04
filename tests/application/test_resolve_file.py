from __future__ import annotations

from application.use_cases.resolve_file import ResolveFile
from domain.entities.archive import Archive
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from tests.fakes import InMemoryArchiveEntryRepository, InMemoryArchiveRepository


async def test_resolve_missing():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    await archives.create(Archive(name="pdmx-mxl-01.tar.gz"))
    await entries.create(
        ArchiveEntry(
            archive_id=1,
            relative_path="mxl/4/5/8/000458.mxl",
            logical_id="K618:MusicXML",
            status=ArchiveEntryStatus.MISSING,
        )
    )
    resolver = ResolveFile(entries, archives)

    resolution = await resolver.execute(relative_path="mxl/4/5/8/000458.mxl")

    assert resolution.found is True
    assert resolution.available is False
    assert resolution.status == "missing"
    assert resolution.archive_name == "pdmx-mxl-01.tar.gz"
    assert resolution.file_id is None


async def test_resolve_ready():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    await archives.create(Archive(name="pdmx-mxl-01.tar.gz"))
    await entries.create(
        ArchiveEntry(
            archive_id=1,
            relative_path="mxl/4/5/8/000458.mxl",
            status=ArchiveEntryStatus.READY,
            file_id=7,
        )
    )
    resolver = ResolveFile(entries, archives)

    resolution = await resolver.execute(relative_path="mxl/4/5/8/000458.mxl")

    assert resolution.found is True
    assert resolution.available is True
    assert resolution.file_id == 7


async def test_resolve_by_logical_id():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    await archives.create(Archive(name="pdmx-mxl-01.tar.gz"))
    await entries.create(
        ArchiveEntry(
            archive_id=1,
            relative_path="mxl/4/5/8/000458.mxl",
            logical_id="K618:MusicXML",
            status=ArchiveEntryStatus.MISSING,
        )
    )
    resolver = ResolveFile(entries, archives)

    resolution = await resolver.execute(logical_id="K618:MusicXML")

    assert resolution.found is True
    assert resolution.relative_path == "mxl/4/5/8/000458.mxl"


async def test_resolve_unknown():
    resolver = ResolveFile(InMemoryArchiveEntryRepository(), InMemoryArchiveRepository())
    resolution = await resolver.execute(relative_path="mxl/no/existe.mxl")
    assert resolution.found is False
    assert resolution.available is False
