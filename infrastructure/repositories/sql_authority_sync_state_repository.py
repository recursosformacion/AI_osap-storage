from __future__ import annotations

import json
from datetime import UTC, datetime

from domain.ports.authority_sync_repository import SyncState

from infrastructure.db.connection import Database


class SqlAuthoritySyncStateRepository:
    """Checkpoint de sincronización por fuente (`authority_sync_state`)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, source: str) -> SyncState:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM authority_sync_state WHERE source = %s", (source,)
            )
            row = await cur.fetchone()
        if row is None:
            return SyncState(source=source)
        metadata = row.get("metadata_json")
        if isinstance(metadata, str) and metadata:
            try:
                metadata = json.loads(metadata)
            except ValueError:
                metadata = None
        return SyncState(
            source=row["source"],
            last_packet=int(row["last_packet"] or 0),
            last_success_at=row.get("last_success_at"),
            last_error=row.get("last_error"),
            metadata=metadata if isinstance(metadata, dict) else None,
        )

    async def save(
        self,
        source: str,
        *,
        last_packet: int | None = None,
        last_success_at: datetime | None = None,
        last_error: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        state = await self.get(source)
        new_packet = last_packet if last_packet is not None else state.last_packet
        new_success = last_success_at if last_success_at is not None else state.last_success_at
        new_error = last_error if last_error is not None else state.last_error
        new_metadata = metadata if metadata is not None else state.metadata
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO authority_sync_state "
                "(source, last_packet, last_success_at, last_error, metadata_json) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE last_packet = VALUES(last_packet), "
                "last_success_at = VALUES(last_success_at), "
                "last_error = VALUES(last_error), "
                "metadata_json = VALUES(metadata_json)",
                (
                    source,
                    new_packet,
                    new_success or datetime.now(UTC),
                    new_error,
                    json.dumps(new_metadata, ensure_ascii=False) if new_metadata else None,
                ),
            )
