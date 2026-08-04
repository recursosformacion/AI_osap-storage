from __future__ import annotations

from domain.entities.storage_provider import ProviderType, StorageProvider
from infrastructure.providers.registry import StorageBackendRegistry


def test_backend_for_without_id_uses_hashable_config_key():
    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, lambda cfg: object())
    provider = StorageProvider(
        name="local",
        provider_type=ProviderType.LOCAL_DISK,
        config={"root": "data/files"},
    )
    first = registry.backend_for(provider)
    second = registry.backend_for(provider)
    assert first is second


def test_backend_for_with_id_is_cached_by_id():
    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, lambda cfg: object())
    provider = StorageProvider(
        name="local",
        provider_type=ProviderType.LOCAL_DISK,
        config={"root": "data/files"},
        id=5,
    )
    assert registry.backend_for(provider) is registry.backend_for(provider)


def test_backend_for_unsupported_type_raises():
    import pytest
    from domain.exceptions import UnsupportedProvider

    registry = StorageBackendRegistry()
    provider = StorageProvider(
        name="x",
        provider_type=ProviderType.S3,
        config={"bucket": "b"},
    )
    with pytest.raises(UnsupportedProvider):
        registry.backend_for(provider)
