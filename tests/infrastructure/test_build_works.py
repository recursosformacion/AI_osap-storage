from __future__ import annotations

from application.use_cases.build_works import BuildWorks, work_key_of
from domain.entities.archive_entry import ArchiveEntry
from tests.fakes import InMemoryArchiveEntryRepository, InMemoryWorkRepository


def test_work_key_of_uses_hash_without_extension():
    assert work_key_of("./mxl/1/1/QmbbKZ9G6.mxl") == "QmbbKZ9G6"
    assert work_key_of("./pdf/1/1/QmbbKZ9G6.pdf") == "QmbbKZ9G6"


async def test_build_works_creates_and_links():
    entries = InMemoryArchiveEntryRepository()
    works = InMemoryWorkRepository()
    await entries.create(
        ArchiveEntry(archive_id=1, relative_path="./mxl/1/1/Qmbb1.mxl", composer="Mozart", title="Ave Verum")
    )
    await entries.create(
        ArchiveEntry(archive_id=1, relative_path="./mxl/1/1/Qmbb2.mxl", composer="Bach", title="BWV")
    )

    result = await BuildWorks(entries, works).execute()

    assert result.works == 2
    assert result.linked == 2
    e1 = await entries.get_by_id(1)
    assert e1.work_id is not None
    work = await works.get_by_id(e1.work_id)
    assert work.composer == "Mozart"
    assert work.title == "Ave Verum"


async def test_build_works_is_idempotent():
    entries = InMemoryArchiveEntryRepository()
    works = InMemoryWorkRepository()
    await entries.create(ArchiveEntry(archive_id=1, relative_path="./mxl/1/1/Qmbb1.mxl", composer="Mozart"))

    uc = BuildWorks(entries, works)
    first = await uc.execute()
    second = await uc.execute()

    assert first.works == 1
    assert second.works == 0
    assert second.linked == 0
    assert await works.count() == 1
