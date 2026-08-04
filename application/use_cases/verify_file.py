from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from domain.entities.storage_location import LocationStatus
from domain.exceptions import EntityNotFound, FileNotAvailable
from domain.ports.hashing import FileHasher
from domain.ports.repositories import (
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.ports.storage import StorageBackendRegistry


@dataclass(frozen=True)
class VerifyItem:
    provider_id: int
    provider_name: str
    expected_sha256: str
    computed_sha256: str | None
    ok: bool


@dataclass(frozen=True)
class VerifyResult:
    file_id: int
    checks: list[VerifyItem]
    ok: bool


class VerifyFile:
    """Recomprueba el SHA256 de cada copia almacenada de un fichero."""

    def __init__(
        self,
        files: FileRepository,
        locations: StorageLocationRepository,
        providers: StorageProviderRepository,
        registry: StorageBackendRegistry,
        hasher: FileHasher,
        temp_dir: str,
    ) -> None:
        self._files = files
        self._locations = locations
        self._providers = providers
        self._registry = registry
        self._hasher = hasher
        self._temp_dir = Path(temp_dir)

    async def execute(self, file_id: int) -> VerifyResult:
        file = await self._files.get_by_id(file_id)
        if file is None:
            raise EntityNotFound("file", file_id)

        locations = await self._locations.list_by_file(file_id)
        stored = [loc for loc in locations if loc.status == LocationStatus.STORED]
        if not stored:
            raise FileNotAvailable(f"file {file_id} has no stored copy to verify")

        checks: list[VerifyItem] = []
        for location in stored:
            checks.append(await self._verify_one(file_id, file.sha256, location))

        return VerifyResult(file_id=file_id, checks=checks, ok=all(c.ok for c in checks))

    async def _verify_one(self, file_id: int, expected: str, location) -> VerifyItem:
        provider = await self._providers.get_by_id(location.provider_id)
        provider_name = provider.name if provider else str(location.provider_id)
        temp = self._temp_dir / f"verify-{file_id}-{location.id}.part"
        computed: str | None = None
        try:
            stream = await self._registry.backend_for(provider).open_stream(location.object_key)
            with open(temp, "wb") as fh:
                async for chunk in stream:
                    fh.write(chunk)
            computed = await self._hasher.sha256_file(str(temp))
        finally:
            if temp.exists():
                temp.unlink()
        return VerifyItem(
            provider_id=location.provider_id,
            provider_name=provider_name,
            expected_sha256=expected,
            computed_sha256=computed,
            ok=computed == expected,
        )
