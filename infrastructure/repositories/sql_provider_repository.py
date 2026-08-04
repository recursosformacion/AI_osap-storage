from __future__ import annotations

import json

from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.ports.repositories import StorageProviderRepository

from infrastructure.db.connection import Database


def _row_to_provider(row: dict) -> StorageProvider:
    return StorageProvider(
        id=row["id"],
        name=row["name"],
        provider_type=ProviderType(row["provider_type"]),
        config=json.loads(row["config"]),
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlStorageProviderRepository(StorageProviderRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, provider: StorageProvider) -> StorageProvider:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO storage_providers (name, provider_type, config, enabled) VALUES (%s, %s, %s, %s)",
                (provider.name, provider.provider_type.value, json.dumps(provider.config), int(provider.enabled)),
            )
            provider.id = cur.lastrowid
            await cur.execute("SELECT * FROM storage_providers WHERE id = %s", (provider.id,))
            return _row_to_provider(await cur.fetchone())

    async def get_by_id(self, provider_id: int) -> StorageProvider | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM storage_providers WHERE id = %s", (provider_id,))
            row = await cur.fetchone()
            return _row_to_provider(row) if row else None

    async def list(self, *, enabled_only: bool = True) -> list[StorageProvider]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            if enabled_only:
                await cur.execute("SELECT * FROM storage_providers WHERE enabled = 1 ORDER BY id")
            else:
                await cur.execute("SELECT * FROM storage_providers ORDER BY id")
            return [_row_to_provider(row) for row in await cur.fetchall()]

    async def save(self, provider: StorageProvider) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE storage_providers SET name = %s, provider_type = %s, config = %s, enabled = %s WHERE id = %s",
                (
                    provider.name,
                    provider.provider_type.value,
                    json.dumps(provider.config),
                    int(provider.enabled),
                    provider.id,
                ),
            )
