from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import UnsupportedProvider
from domain.ports.storage import StorageBackend


class StorageBackendRegistry:
    """Resuelve y cachea el backend físico de cada proveedor persistido."""

    def __init__(self) -> None:
        self._factories: dict[ProviderType, Callable[[dict[str, Any]], StorageBackend]] = {}
        self._instances: dict[tuple, StorageBackend] = {}

    def register(self, provider_type: ProviderType, factory: Callable[[dict[str, Any]], StorageBackend]) -> None:
        self._factories[provider_type] = factory

    def supports(self, provider_type: ProviderType) -> bool:
        return provider_type in self._factories

    def backend_for(self, provider: StorageProvider) -> StorageBackend:
        factory = self._factories.get(provider.provider_type)
        if factory is None:
            raise UnsupportedProvider(
                f"no backend registered for provider type {provider.provider_type.value}"
            )
        key = self._cache_key(provider)
        if key not in self._instances:
            self._instances[key] = factory(provider.config)
        return self._instances[key]

    @staticmethod
    def _cache_key(provider: StorageProvider) -> tuple:
        if provider.id is not None:
            return ("id", provider.id)
        return (
            "config",
            provider.provider_type.value,
            json.dumps(provider.config, sort_keys=True, default=str),
        )
