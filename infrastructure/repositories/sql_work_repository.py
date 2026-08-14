from __future__ import annotations

from domain.entities.work import Work, WorkLists
from domain.ports.work_repository import WorkRepository

from infrastructure.db.connection import Database


def _row_to_work(row: dict) -> Work:
    return Work(
        id=row["id"],
        work_key=row["work_key"],
        composer=row["composer"],
        composer_id=row["composer_id"],
        title=row["title"],
        subtitle=row["subtitle"],
        artist=row["artist"],
        song_name=row["song_name"],
        genre=row["genre"],
        opus=row["opus"],
        catalogue=row["catalogue"],
        musical_key=row["musical_key"],
        year=row["year"],
        instrumentation=row["instrumentation"],
        language=row["language"],
        tags=row["tags"],
        duration=row["duration"],
        measures=row["measures"],
        pages=row["pages"],
        parts=row["parts"],
        complexity=row["complexity"],
        license=row["license"],
        public_domain=bool(row["public_domain"]),
        description=row["description"],
        thumbnails=row["thumbnails"],
        relative_path=row["relative_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlWorkRepository(WorkRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, work: Work) -> Work:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO works (work_key, relative_path, composer, composer_id, title, tags) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (work.work_key, work.relative_path, work.composer, work.composer_id, work.title, work.tags),
            )
            work.id = cur.lastrowid
            return work

    async def update(self, work: Work) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE works SET relative_path=%s, composer=%s, composer_id=%s, title=%s, "
                "subtitle=%s, artist=%s, song_name=%s, genre=%s, opus=%s, catalogue=%s, "
                "musical_key=%s, year=%s, instrumentation=%s, language=%s, tags=%s, "
                "duration=%s, measures=%s, pages=%s, parts=%s, complexity=%s, license=%s, "
                "public_domain=%s, description=%s, thumbnails=%s WHERE id=%s",
                (
                    work.relative_path,
                    work.composer,
                    work.composer_id,
                    work.title,
                    work.subtitle,
                    work.artist,
                    work.song_name,
                    work.genre,
                    work.opus,
                    work.catalogue,
                    work.musical_key,
                    work.year,
                    work.instrumentation,
                    work.language,
                    work.tags,
                    work.duration,
                    work.measures,
                    work.pages,
                    work.parts,
                    work.complexity,
                    work.license,
                    int(work.public_domain),
                    work.description,
                    work.thumbnails,
                    work.id,
                ),
            )

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
        prefix = f"{query}%"
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT *, CASE "
                "  WHEN title = %s THEN 100 "
                "  WHEN title LIKE %s THEN 90 "
                "  WHEN title LIKE %s THEN 70 "
                "  WHEN composer LIKE %s THEN 40 "
                "  WHEN catalogue LIKE %s THEN 30 "
                "  ELSE 0 END AS score "
                "FROM works WHERE composer LIKE %s OR title LIKE %s OR catalogue LIKE %s "
                "ORDER BY score DESC, id LIMIT %s OFFSET %s",
                (query, prefix, pattern, pattern, pattern,
                 pattern, pattern, pattern, limit, offset),
            )
            return [_row_to_work(row) for row in await cur.fetchall()]

    async def all_(self, *, limit: int = 100, offset: int = 0) -> list[Work]:
        return await self.list_all(limit=limit, offset=offset)

    async def list_all(self, *, limit: int = 1000, offset: int = 0) -> list[Work]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM works ORDER BY id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_work(row) for row in await cur.fetchall()]

    async def list_by_composer(
        self, composer_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[Work]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM works WHERE composer_id = %s ORDER BY id LIMIT %s OFFSET %s",
                (composer_id, limit, offset),
            )
            return [_row_to_work(row) for row in await cur.fetchall()]

    async def count(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM works")
            return int((await cur.fetchone())["total"])

    async def _replace(self, table: str, column: str, work_id: int, values: list[str]) -> None:
        unique = list(dict.fromkeys(v.strip() for v in values if v and v.strip()))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"DELETE FROM {table} WHERE work_id = %s", (work_id,))
            if unique:
                placeholders = ", ".join(["(%s, %s)"] * len(unique))
                params: list = []
                for value in unique:
                    params.extend([work_id, value])
                await cur.execute(
                    f"INSERT INTO {table} (work_id, {column}) VALUES {placeholders}",
                    params,
                )

    async def replace_tags(self, work_id: int, tags: list[str]) -> None:
        await self._replace("work_tags", "tag", work_id, tags)

    async def replace_genres(self, work_id: int, genres: list[str]) -> None:
        await self._replace("work_genres", "genre", work_id, genres)

    async def replace_instruments(self, work_id: int, instruments: list[str]) -> None:
        await self._replace("work_instruments", "instrument", work_id, instruments)

    async def replace_parts(self, work_id: int, parts: list[str]) -> None:
        await self._replace("work_parts", "part_name", work_id, parts)

    async def _get_list(self, table: str, column: str, work_id: int) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT {column} FROM {table} WHERE work_id = %s ORDER BY id",
                (work_id,),
            )
            return [row[column] for row in await cur.fetchall()]

    async def get_tags(self, work_id: int) -> list[str]:
        return await self._get_list("work_tags", "tag", work_id)

    async def get_genres(self, work_id: int) -> list[str]:
        return await self._get_list("work_genres", "genre", work_id)

    async def get_instruments(self, work_id: int) -> list[str]:
        return await self._get_list("work_instruments", "instrument", work_id)

    async def get_parts(self, work_id: int) -> list[str]:
        return await self._get_list("work_parts", "part_name", work_id)

    async def get_lists_bulk(self, work_ids: list[int]) -> dict[int, WorkLists]:
        if not work_ids:
            return {}
        result: dict[int, WorkLists] = {wid: WorkLists() for wid in work_ids}
        placeholders = ", ".join(["%s"] * len(work_ids))
        for table, column, attr in (
            ("work_tags", "tag", "tags"),
            ("work_genres", "genre", "genres"),
            ("work_instruments", "instrument", "instruments"),
            ("work_parts", "part_name", "parts_names"),
        ):
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    f"SELECT work_id, {column} AS v FROM {table} WHERE work_id IN ({placeholders}) ORDER BY id",
                    work_ids,
                )
                for row in await cur.fetchall():
                    getattr(result[row["work_id"]], attr).append(row["v"])
        return result
