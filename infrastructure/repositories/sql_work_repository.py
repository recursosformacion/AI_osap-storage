from __future__ import annotations

from domain.entities.work import Work
from domain.ports.work_repository import WorkRepository

from infrastructure.db.connection import Database


def _row_to_work(row: dict) -> Work:
    return Work(
        id=row["id"],
        work_key=row["work_key"],
        composer=row["composer"],
        title=row["title"],
        genre=row["genre"],
        opus=row["opus"],
        catalogue=row["catalogue"],
        musical_key=row["musical_key"],
        year=row["year"],
        instrumentation=row["instrumentation"],
        language=row["language"],
        tags=row["tags"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlWorkRepository(WorkRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, work: Work) -> Work:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO works (work_key, composer, title, genre, opus, catalogue, musical_key, "
                "year, instrumentation, language, tags) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    work.work_key,
                    work.composer,
                    work.title,
                    work.genre,
                    work.opus,
                    work.catalogue,
                    work.musical_key,
                    work.year,
                    work.instrumentation,
                    work.language,
                    work.tags,
                ),
            )
            work.id = cur.lastrowid
            return work

    async def get_by_id(self, work_id: int) -> Work | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM works WHERE id = %s", (work_id,))
            row = await cur.fetchone()
            return _row_to_work(row) if row else None

    async def get_by_work_key(self, work_key: str) -> Work | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM works WHERE work_key = %s", (work_key,))
            row = await cur.fetchone()
            return _row_to_work(row) if row else None

    async def search(self, query: str, *, limit: int = 50, offset: int = 0) -> list[Work]:
        pattern = f"%{query}%"
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM works WHERE composer LIKE %s OR title LIKE %s "
                "OR catalogue LIKE %s ORDER BY id LIMIT %s OFFSET %s",
                (pattern, pattern, pattern, limit, offset),
            )
            return [_row_to_work(row) for row in await cur.fetchall()]

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Work]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM works ORDER BY id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_work(row) for row in await cur.fetchall()]

    async def count(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM works")
            return int((await cur.fetchone())["total"])
