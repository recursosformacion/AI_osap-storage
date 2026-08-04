from __future__ import annotations

from application.services.mirror_resources import MirrorResourceRegistrar
from application.use_cases.register_resources import (
    RegisterMirrorResources,
    RegisterMirrorResourcesCommand,
)
from domain.entities.archive import Archive
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.storage_location import LocationStatus
from domain.entities.storage_provider import ProviderType, StorageProvider
from tests.fakes import (
    InMemoryArchiveEntryRepository,
    InMemoryArchiveRepository,
    InMemoryFileRepository,
    InMemoryLocationRepository,
    InMemoryProviderRepository,
)


async def test_register_resources_creates_file_and_location():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    files = InMemoryFileRepository()
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()
    provider = await providers.create(
        StorageProvider(name="mirror", provider_type=ProviderType.LOCAL_DISK, config={})
    )
    await archives.create(Archive(name="mxl.tar.gz"))
    entry_a = await entries.create(
        ArchiveEntry(archive_id=1, relative_path="./mxl/1/11/a.mxl", logical_id="A")
    )
    await entries.create(ArchiveEntry(archive_id=1, relative_path="./mxl/1/11/b.mxl", logical_id="B"))

    registrar = MirrorResourceRegistrar(files, locations, entries)
    use_case = RegisterMirrorResources(archives, entries, providers, registrar)

    result = await use_case.execute(
        RegisterMirrorResourcesCommand(archive_id=1, provider_id=provider.id)
    )

    assert result.files == 2
    assert result.locations == 2
    assert await files.count() == 2
    assert await locations.count() == 2

    linked_a = await entries.get_by_id(entry_a.id)
    assert linked_a.file_id is not None
    file_a = await files.get_by_id(linked_a.file_id)
    assert file_a.sha256 is None  # sin hashear: el mirror ya es el almacenamiento
    assert file_a.name == "a.mxl"

    location = (await locations.list_by_file(linked_a.file_id))[0]
    assert location.provider_id == provider.id
    assert location.object_key == "./mxl/1/11/a.mxl"
    assert location.status == LocationStatus.STORED


async def test_register_resources_is_idempotent():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    files = InMemoryFileRepository()
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()
    await providers.create(StorageProvider(name="mirror", provider_type=ProviderType.LOCAL_DISK, config={}))
    await archives.create(Archive(name="mxl.tar.gz"))
    await entries.create(
        ArchiveEntry(archive_id=1, relative_path="./mxl/a.mxl", status=ArchiveEntryStatus.READY)
    )

    registrar = MirrorResourceRegistrar(files, locations, entries)
    use_case = RegisterMirrorResources(archives, entries, providers, registrar)

    await use_case.execute(RegisterMirrorResourcesCommand(archive_id=1, provider_id=1))
    second = await use_case.execute(RegisterMirrorResourcesCommand(archive_id=1, provider_id=1))

    assert second.files == 0  # ya tiene file_id
    assert await files.count() == 1
    assert await locations.count() == 1
