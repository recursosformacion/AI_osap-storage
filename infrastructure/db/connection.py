from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiomysql

from infrastructure.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: aiomysql.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = await aiomysql.create_pool(
            host=self._settings.db_host,
            port=self._settings.db_port,
            user=self._settings.db_user,
            password=self._settings.db_password,
            db=self._settings.db_name,
            charset="utf8mb4",
            autocommit=True,
            maxsize=self._settings.db_pool_size,
            minsize=1,
            cursorclass=aiomysql.DictCursor,
        )

    async def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiomysql.Connection]:
        await self.connect()
        async with self._pool.acquire() as conn:
            yield conn
