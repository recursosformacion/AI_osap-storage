from __future__ import annotations

from domain.ports.musicbrainz_cache_repository import MusicBrainzCacheRepository

from infrastructure.db.connection import Database


class SqlMusicBrainzCacheRepository(MusicBrainzCacheRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, query: str) -> str | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT payload FROM musicbrainz_cache WHERE query_key = %s", (query,)
            )
            row = await cur.fetchone()
            return row["payload"] if row else None

    async def set(self, query: str, payload: str) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO musicbrainz_cache (query_key, payload) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE payload = VALUES(payload)",
                (query, payload),
            )
