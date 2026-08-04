from __future__ import annotations

from types import SimpleNamespace

from domain.entities.storage_location import StorageLocation
from domain.entities.storage_provider import ProviderType, StorageProvider
from infrastructure.doctor import check_index_links
from infrastructure.providers.registry import StorageBackendRegistry
from tests.fakes import InMemoryLocationRepository, InMemoryProviderRepository, MemoryBackend


async def test_check_index_links_reports_missing():
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()
    await providers.create(
        StorageProvider(name="mem", provider_type=ProviderType.LOCAL_DISK, config={})
    )
    backend = MemoryBackend({})
    backend._objects["./mxl/a.mxl"] = b"<score/>"

    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, lambda cfg: backend)

    await locations.create(StorageLocation(file_id=1, provider_id=1, object_key="./mxl/a.mxl"))
    await locations.create(StorageLocation(file_id=2, provider_id=1, object_key="./mxl/falta.mxl"))

    container = SimpleNamespace(location_repo=locations, provider_repo=providers, registry=registry)
    report = await check_index_links(container)

    assert report.checked == 2
    assert report.found == 1
    assert report.missing == 1
    assert report.missing_samples == ["./mxl/falta.mxl"]


async def test_check_index_links_all_present():
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()
    await providers.create(
        StorageProvider(name="mem", provider_type=ProviderType.LOCAL_DISK, config={})
    )
    backend = MemoryBackend({})
    backend._objects["./mxl/a.mxl"] = b"x"

    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, lambda cfg: backend)

    await locations.create(StorageLocation(file_id=1, provider_id=1, object_key="./mxl/a.mxl"))

    container = SimpleNamespace(location_repo=locations, provider_repo=providers, registry=registry)
    report = await check_index_links(container)

    assert report.checked == 1
    assert report.missing == 0
