from __future__ import annotations

import hashlib

import pytest
from application.services.file_publisher import FilePublisher
from application.services.tar_downloader import TarDownloader
from application.use_cases.materialize_file import MaterializeFile, MaterializeFileCommand
from domain.entities.archive import Archive, ArchiveStatus
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.storage_location import LocationStatus
from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import EntityNotFound, InvalidFileData
from domain.services.file_registration import FileRegistrationService
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

PAYLOAD = b"<score>X</score>"
SHA = hashlib.sha256(PAYLOAD).hexdigest()


async def build(tmp_path, files: dict[str, bytes]):
    files_repo = InMemoryFileRepository()
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()
    await providers.create(StorageProvider(name="mem", provider_type=ProviderType.LOCAL_DISK, config={}))
    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, MemoryBackend)
    publisher = FilePublisher(files_repo, locations, providers, registry)
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    use_case = MaterializeFile(
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


async def test_materialize_file_downloads_and_publishes(tmp_path):
    use_case, archives, entries, files_repo, locations = await build(tmp_path, {"mxl/a.mxl": PAYLOAD})
    archive = await archives.create(Archive(name="p.tar.gz", url="https://src/p.tar.gz"))
    await entries.create(
        ArchiveEntry(archive_id=archive.id, relative_path="mxl/a.mxl", logical_id="K1")
    )
    cache = tmp_path / "cache"
    use_case._tar_downloader = TarDownloader(FakeDownloader(b"tar"), str(cache))

    result = await use_case.execute(MaterializeFileCommand(logical_id="K1", provider_id=1))

    assert result.file.sha256 == SHA
    assert result.entry.status == ArchiveEntryStatus.READY
    assert result.entry.file_id == result.file.id
    assert result.published.provider.id == 1
    stored = await locations.list_by_file(result.file.id)
    assert stored and stored[0].status == LocationStatus.STORED
    updated = await archives.get_by_id(archive.id)
    assert updated.local_path == str(cache / "p.tar.gz")
    assert updated.status == ArchiveStatus.DOWNLOADED


async def test_materialize_file_reuses_cached_tar(tmp_path):
    use_case, archives, entries, files_repo, locations = await build(tmp_path, {"mxl/a.mxl": PAYLOAD})
    cache = tmp_path / "cache"
    cached_tar = cache / "p.tar.gz"
    cached_tar.parent.mkdir(parents=True, exist_ok=True)
    cached_tar.write_bytes(b"tar ya presente")
    archive = await archives.create(Archive(name="p.tar.gz", url="https://src/p.tar.gz", local_path=str(cached_tar)))
    await entries.create(ArchiveEntry(archive_id=archive.id, relative_path="mxl/a.mxl"))

    # download=False: debe usar el TAR ya en caché sin descargar
    result = await use_case.execute(MaterializeFileCommand(relative_path="mxl/a.mxl", provider_id=1, download=False))

    assert result.entry.status == ArchiveEntryStatus.READY


async def test_materialize_file_unknown_logical_id_raises(tmp_path):
    use_case, archives, entries, _, _ = await build(tmp_path, {})
    with pytest.raises(EntityNotFound):
        await use_case.execute(MaterializeFileCommand(logical_id="NOEXISTE"))


async def test_materialize_file_requires_selector(tmp_path):
    use_case, _, _, _, _ = await build(tmp_path, {})
    with pytest.raises(InvalidFileData):
        await use_case.execute(MaterializeFileCommand())


async def test_materialize_file_no_download_without_local_raises(tmp_path):
    use_case, archives, entries, _, _ = await build(tmp_path, {})
    archive = await archives.create(Archive(name="p.tar.gz", url="https://src/p.tar.gz"))
    await entries.create(ArchiveEntry(archive_id=archive.id, relative_path="mxl/a.mxl"))
    with pytest.raises(InvalidFileData):
        await use_case.execute(MaterializeFileCommand(relative_path="mxl/a.mxl", download=False))
