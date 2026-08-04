from __future__ import annotations

import hashlib

import pytest
from application.services.file_publisher import FilePublisher
from application.services.tar_downloader import TarDownloader
from application.use_cases.materialize_archive import MaterializeArchive, MaterializeArchiveCommand
from domain.entities.archive import Archive, ArchiveStatus
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.storage_location import LocationStatus
from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import EntityNotFound, InvalidFileData
from domain.services.file_registration import FileRegistrationService
from infrastructure.archives.factory import ArchiveReaderFactory
from infrastructure.hashing.hashlib_hasher import HashlibHasher
from infrastructure.providers.registry import StorageBackendRegistry
from tests.fakes import (
    FakeArchiveReaderFactory,
    FakeDownloader,
    InMemoryArchiveEntryRepository,
    InMemoryArchiveRepository,
    InMemoryFileRepository,
    InMemoryLocationRepository,
    InMemoryProviderRepository,
    MemoryBackend,
)

PAYLOAD_A = b"<score>A</score>"
PAYLOAD_B = b"<score>B</score>"
SHA_A = hashlib.sha256(PAYLOAD_A).hexdigest()
SHA_B = hashlib.sha256(PAYLOAD_B).hexdigest()


async def build_use_case(tmp_path, files: dict[str, bytes]):
    files_repo = InMemoryFileRepository()
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()
    await providers.create(StorageProvider(name="mem", provider_type=ProviderType.LOCAL_DISK, config={}))

    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, MemoryBackend)

    publisher = FilePublisher(files_repo, locations, providers, registry)
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()

    use_case = MaterializeArchive(
        archives=archives,
        entries=entries,
        reader_factory=FakeArchiveReaderFactory(files),
        hasher=HashlibHasher(),
        registration=FileRegistrationService(files_repo),
        publisher=publisher,
        temp_dir=str(tmp_path),
        tar_downloader=TarDownloader(None, None),
    )
    return use_case, archives, entries, files_repo, locations


async def test_materialize_publishes_every_entry(tmp_path):
    files = {
        "mxl/a.mxl": PAYLOAD_A,
        "mxl/b.mxl": PAYLOAD_B,
    }
    use_case, archives, entries, files_repo, locations = await build_use_case(tmp_path, files)
    dummy = tmp_path / "p.tar.gz"
    dummy.write_bytes(b"dummy")
    await archives.create(Archive(name="p.tar.gz", local_path=str(dummy)))
    await entries.create(ArchiveEntry(archive_id=1, relative_path="mxl/a.mxl"))
    await entries.create(ArchiveEntry(archive_id=1, relative_path="mxl/b.mxl"))

    result = await use_case.execute(MaterializeArchiveCommand(archive_id=1, provider_id=1))

    assert result.total == 2
    assert result.ready == 2
    assert result.failed == 0

    entry_a = await entries.get_by_id(1)
    assert entry_a.status == ArchiveEntryStatus.READY
    assert entry_a.file_id is not None
    file_a = await files_repo.get_by_id(entry_a.file_id)
    assert file_a.sha256 == SHA_A

    stored = await locations.list_by_file(entry_a.file_id)
    assert stored and stored[0].status == LocationStatus.STORED

    archive = await archives.get_by_id(1)
    assert archive.status == ArchiveStatus.MATERIALIZED


async def test_materialize_deduplicates_files_by_sha256(tmp_path):
    files = {"mxl/a.mxl": PAYLOAD_A, "mxl/c.mxl": PAYLOAD_A}
    use_case, archives, entries, files_repo, _ = await build_use_case(tmp_path, files)
    dummy = tmp_path / "p.tar.gz"
    dummy.write_bytes(b"dummy")
    await archives.create(Archive(name="p.tar.gz", local_path=str(dummy)))
    await entries.create(ArchiveEntry(archive_id=1, relative_path="mxl/a.mxl"))
    await entries.create(ArchiveEntry(archive_id=1, relative_path="mxl/c.mxl"))

    result = await use_case.execute(MaterializeArchiveCommand(archive_id=1, provider_id=1))

    assert result.ready == 2
    assert await files_repo.count() == 1  # mismo contenido -> mismo File


async def test_materialize_fails_entries_missing_in_tar(tmp_path):
    files = {"mxl/a.mxl": PAYLOAD_A}
    use_case, archives, entries, files_repo, _ = await build_use_case(tmp_path, files)
    dummy = tmp_path / "p.tar.gz"
    dummy.write_bytes(b"dummy")
    await archives.create(Archive(name="p.tar.gz", local_path=str(dummy)))
    await entries.create(ArchiveEntry(archive_id=1, relative_path="mxl/a.mxl"))
    await entries.create(ArchiveEntry(archive_id=1, relative_path="mxl/ausente.mxl"))

    result = await use_case.execute(MaterializeArchiveCommand(archive_id=1, provider_id=1))

    assert result.ready == 1
    assert result.failed == 1
    missing = await entries.get_by_id(2)
    assert missing.status == ArchiveEntryStatus.FAILED


async def test_materialize_requires_local_path(tmp_path):
    use_case, archives, entries, _, _ = await build_use_case(tmp_path, {})
    await archives.create(Archive(name="p.tar.gz"))

    with pytest.raises(InvalidFileData):
        await use_case.execute(MaterializeArchiveCommand(archive_id=1, provider_id=1))


async def test_materialize_unknown_archive_raises(tmp_path):
    use_case, _, _, _, _ = await build_use_case(tmp_path, {})
    with pytest.raises(EntityNotFound):
        await use_case.execute(MaterializeArchiveCommand(archive_id=999))


async def test_materialize_from_extracted_directory(tmp_path):
    use_case, archives, entries, files_repo, _ = await build_use_case(tmp_path, {})
    use_case._reader_factory = ArchiveReaderFactory()

    content_root = tmp_path / "content"
    (content_root / "mxl").mkdir(parents=True)
    (content_root / "mxl" / "a.mxl").write_bytes(PAYLOAD_A)
    (content_root / "mxl" / "b.mxl").write_bytes(PAYLOAD_B)

    await archives.create(
        Archive(name="mxl.tar.gz", format="directory", local_path=str(content_root))
    )
    await entries.create(ArchiveEntry(archive_id=1, relative_path="./mxl/a.mxl"))
    await entries.create(ArchiveEntry(archive_id=1, relative_path="./mxl/b.mxl"))

    result = await use_case.execute(MaterializeArchiveCommand(archive_id=1, provider_id=1))

    assert result.total == 2
    assert result.ready == 2
    assert result.failed == 0


async def test_materialize_downloads_tar_into_cache(tmp_path):
    use_case, archives, entries, files_repo, _ = await build_use_case(
        tmp_path, {"mxl/a.mxl": PAYLOAD_A, "mxl/b.mxl": PAYLOAD_B}
    )
    archive = await archives.create(Archive(name="p.tar.gz", url="https://src/p.tar.gz"))
    await entries.create(ArchiveEntry(archive_id=archive.id, relative_path="mxl/a.mxl"))
    await entries.create(ArchiveEntry(archive_id=archive.id, relative_path="mxl/b.mxl"))

    cache = tmp_path / "cache"
    use_case._tar_downloader = TarDownloader(FakeDownloader(b"contenido tar"), str(cache))

    result = await use_case.execute(
        MaterializeArchiveCommand(archive_id=archive.id, provider_id=1, download=True)
    )

    assert result.ready == 2
    cached_tar = cache / "p.tar.gz"
    assert cached_tar.exists()  # TAR descargado a la caché
    updated = await archives.get_by_id(archive.id)
    assert updated.local_path == str(cached_tar)
    assert updated.status == ArchiveStatus.MATERIALIZED


async def test_materialize_can_discard_tar_after(tmp_path):
    use_case, archives, entries, files_repo, _ = await build_use_case(tmp_path, {"mxl/a.mxl": PAYLOAD_A})
    archive = await archives.create(Archive(name="p.tar.gz", url="https://src/p.tar.gz"))
    await entries.create(ArchiveEntry(archive_id=archive.id, relative_path="mxl/a.mxl"))

    cache = tmp_path / "cache"
    use_case._tar_downloader = TarDownloader(FakeDownloader(b"tar"), str(cache))

    result = await use_case.execute(
        MaterializeArchiveCommand(archive_id=archive.id, provider_id=1, download=True, keep_tar=False)
    )

    assert result.ready == 1
    assert not (cache / "p.tar.gz").exists()  # TAR eliminado de la caché
    updated = await archives.get_by_id(archive.id)
    assert updated.local_path is None


async def test_materialize_download_without_downloader_raises(tmp_path):
    use_case, archives, entries, _, _ = await build_use_case(tmp_path, {})
    archive = await archives.create(Archive(name="p.tar.gz", url="https://src/p.tar.gz"))
    await entries.create(ArchiveEntry(archive_id=archive.id, relative_path="mxl/a.mxl"))

    with pytest.raises(InvalidFileData):
        await use_case.execute(MaterializeArchiveCommand(archive_id=archive.id, download=True))
