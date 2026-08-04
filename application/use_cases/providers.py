from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import EntityNotFound
from domain.ports.repositories import StorageProviderRepository
from domain.ports.storage import StorageBackendRegistry


@dataclass(frozen=True)
class CreateProviderCommand:
    name: str
    provider_type: ProviderType
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


class CreateProvider:
    def __init__(
        self,
        providers: StorageProviderRepository,
        registry: StorageBackendRegistry,
    ) -> None:
        self._providers = providers
        self._registry = registry

    async def execute(self, command: CreateProviderCommand) -> StorageProvider:
        provider = StorageProvider(
            name=command.name,
            provider_type=command.provider_type,
            config=command.config,
            enabled=command.enabled,
        )
        # Valida que exista un backend para el tipo y que la config sea aceptable.
        self._registry.backend_for(provider)
        return await self._providers.create(provider)


class ListProviders:
    def __init__(self, providers: StorageProviderRepository) -> None:
        self._providers = providers

    async def execute(self, *, enabled_only: bool = False) -> list[StorageProvider]:
        return await self._providers.list(enabled_only=enabled_only)


class GetProvider:
    def __init__(self, providers: StorageProviderRepository) -> None:
        self._providers = providers

    async def execute(self, provider_id: int) -> StorageProvider:
        provider = await self._providers.get_by_id(provider_id)
        if provider is None:
            raise EntityNotFound("storage_provider", provider_id)
        return provider
