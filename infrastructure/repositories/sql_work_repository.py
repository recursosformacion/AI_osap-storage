from __future__ import annotations

from domain.entities.work import Work, WorkLists
from domain.ports.work_repository import WorkRepository

from infrastructure.db.connection import Database

# Roles de `works_person_roles`: 1 = Composer, 10 = Intérprete/Solista (ver tabla `roles`).
ROLE_COMPOSER = 1
ROLE_PERFORMER = 10

# Campos derivados de las relaciones del esquema nuevo (compositor, artista, género,
# instrumentación, tags e idioma ya no viven en `works`).
_DERIVED = """
    (SELECT p.persons_name FROM works_person_roles r
       JOIN persons p ON p.persons_id = r.works_person_roles_person_id
      WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = %(composer_role)s
      ORDER BY r.works_person_roles_order, r.works_person_roles_id LIMIT 1) AS composer,
    (SELECT r.works_person_roles_person_id FROM works_person_roles r
      WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = %(composer_role)s
      ORDER BY r.works_person_roles_order, r.works_person_roles_id LIMIT 1) AS person_id,
    (SELECT GROUP_CONCAT(DISTINCT p.persons_name ORDER BY p.persons_name SEPARATOR ', ')
       FROM works_person_roles r
       JOIN persons p ON p.persons_id = r.works_person_roles_person_id
      WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = %(performer_role)s) AS artist,
    (SELECT GROUP_CONCAT(DISTINCT g.name ORDER BY g.name SEPARATOR ', ')
       FROM work_genres wg JOIN genres g ON g.id = wg.genres_id
      WHERE wg.works_id = w.id) AS genre,
    (SELECT GROUP_CONCAT(DISTINCT i.name_en ORDER BY i.name_en SEPARATOR ', ')
       FROM work_instruments wi JOIN instruments i ON i.id = wi.instruments_id
      WHERE wi.works_id = w.id) AS instrumentation,
    (SELECT GROUP_CONCAT(DISTINCT tg.tag_texto ORDER BY tg.tag_texto SEPARATOR ', ')
       FROM work_tag wt JOIN tag_work tg ON tg.id = wt.tag_id
      WHERE wt.works_id = w.id) AS tags,
    (SELECT GROUP_CONCAT(DISTINCT l.languages_code ORDER BY l.languages_code SEPARATOR ', ')
       FROM work_language wl JOIN languages l ON l.id = wl.languages_id
      WHERE wl.works_id = w.id) AS language
"""

_SELECT_ONE = f"SELECT w.*, {_DERIVED} FROM works w"
_SELECT_PARAMS = {"composer_role": ROLE_COMPOSER, "performer_role": ROLE_PERFORMER}


def _row_to_work(row: dict) -> Work:
    return Work(
        id=row["id"],
        work_key=row.get("works_key"),
        composer=row.get("composer"),
        person_id=row.get("person_id"),
        attribution_type=row.get("works_attr_type"),
        attribution_note=row.get("works_attribution_note"),
        title=row.get("works_title"),
        subtitle=row.get("works_subtitle"),
        artist=row.get("artist"),
        song_name=row.get("works_song_name"),
        genre=row.get("genre"),
        opus=row.get("works_opus"),
        catalogue=row.get("works_catalogue"),
        musical_key=row.get("works_musical_key"),
        year=row.get("works_year"),
        instrumentation=row.get("instrumentation"),
        language=row.get("language"),
        tags=row.get("tags"),
        duration=row.get("works_duration"),
        measures=row.get("works_measures"),
        pages=row.get("works_pages"),
        parts=row.get("works_parts"),
        complexity=row.get("works_complexity"),
        license=row.get("works_license"),
        public_domain=bool(row.get("works_public_domain")),
        description=row.get("works_description"),
        relative_path=row.get("works_relative_path"),
        origin=row.get("works_origin"),
        origin_id=row.get("works_origin_id"),
        voicing=row.get("works_voicing"),
        created_at=row.get("works_created_at"),
        updated_at=row.get("works_updated_at"),
    )


async def _resolve_genre(cur, name: str) -> int | None:
    code = (name or "").strip()
    if not code:
        return None
    await cur.execute("SELECT genre_id FROM genre_mappings WHERE code = %s LIMIT 1", (code,))
    row = await cur.fetchone()
    if row:
        return int(row["genre_id"])
    await cur.execute("SELECT id FROM genres WHERE name = %s LIMIT 1", (code,))
    row = await cur.fetchone()
    return int(row["id"]) if row else None


async def _resolve_instrument(cur, name: str) -> int | None:
    key = (name or "").strip()
    if not key:
        return None
    await cur.execute(
        "SELECT id FROM instruments WHERE code = %s OR name_en = %s OR name_es = %s "
        "OR JSON_CONTAINS(COALESCE(aliases, '[]'), JSON_QUOTE(%s)) LIMIT 1",
        (key, key, key, key),
    )
    row = await cur.fetchone()
    return int(row["id"]) if row else None


class SqlWorkRepository(WorkRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, work: Work) -> Work:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO works (works_key, works_relative_path, works_attr_type, "
                "works_attribution_note, works_title, works_song_name, works_subtitle, "
                "works_opus, works_catalogue, works_musical_key, works_year, works_duration, "
                "works_measures, works_pages, works_parts, works_complexity, works_description, "
                "works_license, works_public_domain, works_origin, works_origin_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s)",
                (
                    work.work_key, work.relative_path, work.attribution_type,
                    work.attribution_note, work.title, work.song_name, work.subtitle,
                    work.opus, work.catalogue, work.musical_key, work.year, work.duration,
                    work.measures, work.pages, work.parts, work.complexity, work.description,
                    work.license, int(work.public_domain), None, None,
                ),
            )
            work.id = cur.lastrowid
            if work.person_id:
                await cur.execute(
                    "INSERT IGNORE INTO works_person_roles (works_person_roles_work_id, "
                    "works_person_roles_person_id, works_person_roles_role_id) "
                    "VALUES (%s, %s, %s)",
                    (work.id, work.person_id, ROLE_COMPOSER),
                )
            return work

    async def update(self, work: Work) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE works SET works_relative_path=%s, works_attr_type=%s, "
                "works_attribution_note=%s, works_title=%s, works_song_name=%s, "
                "works_subtitle=%s, works_opus=%s, works_catalogue=%s, works_musical_key=%s, "
                "works_year=%s, works_duration=%s, works_measures=%s, works_pages=%s, "
                "works_parts=%s, works_complexity=%s, works_description=%s, works_license=%s, "
                "works_public_domain=%s WHERE id=%s",
                (
                    work.relative_path, work.attribution_type, work.attribution_note,
                    work.title, work.song_name, work.subtitle, work.opus, work.catalogue,
                    work.musical_key, work.year, work.duration, work.measures, work.pages,
                    work.parts, work.complexity, work.description, work.license,
                    int(work.public_domain), work.id,
                ),
            )
            if work.person_id:
                await cur.execute(
                    "INSERT IGNORE INTO works_person_roles (works_person_roles_work_id, "
                    "works_person_roles_person_id, works_person_roles_role_id) "
                    "VALUES (%s, %s, %s)",
                    (work.id, work.person_id, ROLE_COMPOSER),
                )

    async def get_by_id(self, work_id: int) -> Work | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"{_SELECT_ONE} WHERE w.id = %(id)s", {**_SELECT_PARAMS, "id": work_id})
            row = await cur.fetchone()
            return _row_to_work(row) if row else None

    async def get_by_work_key(self, work_key: str) -> Work | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"{_SELECT_ONE} WHERE w.works_key = %(key)s", {**_SELECT_PARAMS, "key": work_key}
            )
            row = await cur.fetchone()
            return _row_to_work(row) if row else None

    async def search(
        self, query: str, *, limit: int = 50, offset: int = 0, origins: list[str] | None = None
    ) -> list[Work]:
        pattern = f"%{query}%"
        prefix = f"{query}%"
        params: dict = {
            **_SELECT_PARAMS,
            "query": query,
            "prefix": prefix,
            "pattern": pattern,
            "limit": limit,
            "offset": offset,
        }
        origin_clause = ""
        if origins:
            origin_clause = "AND w.works_origin IN (" + ", ".join(
                f"%(origin{i})s" for i in range(len(origins))
            ) + ")"
            params.update({f"origin{i}": value for i, value in enumerate(origins)})
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"{_SELECT_ONE} WHERE ("
                "w.works_title = %(query)s OR w.works_title LIKE %(prefix)s "
                "OR w.works_title LIKE %(pattern)s "
                "OR w.works_catalogue LIKE %(pattern)s "
                "OR w.works_attr_type LIKE %(pattern)s "
                "OR w.works_attribution_note LIKE %(pattern)s "
                "OR EXISTS (SELECT 1 FROM works_person_roles r JOIN persons p "
                "  ON p.persons_id = r.works_person_roles_person_id "
                "  WHERE r.works_person_roles_work_id = w.id AND p.persons_name LIKE %(pattern)s)) "
                f"{origin_clause} "
                "ORDER BY (CASE WHEN w.works_title = %(query)s THEN 100 "
                "  WHEN w.works_title LIKE %(prefix)s THEN 90 "
                "  WHEN w.works_title LIKE %(pattern)s THEN 70 "
                "  ELSE 40 END) DESC, w.id "
                "LIMIT %(limit)s OFFSET %(offset)s",
                params,
            )
            return [_row_to_work(row) for row in await cur.fetchall()]

    async def all_(
        self, *, limit: int = 100, offset: int = 0, origins: list[str] | None = None
    ) -> list[Work]:
        return await self.list_all(limit=limit, offset=offset, origins=origins)

    async def list_all(
        self, *, limit: int = 1000, offset: int = 0, origins: list[str] | None = None
    ) -> list[Work]:
        params: dict = {**_SELECT_PARAMS, "limit": limit, "offset": offset}
        origin_clause = ""
        if origins:
            origin_clause = "WHERE w.works_origin IN (" + ", ".join(
                f"%(origin{i})s" for i in range(len(origins))
            ) + ")"
            params.update({f"origin{i}": value for i, value in enumerate(origins)})
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"{_SELECT_ONE} {origin_clause} ORDER BY w.id LIMIT %(limit)s OFFSET %(offset)s",
                params,
            )
            return [_row_to_work(row) for row in await cur.fetchall()]

    async def list_by_composer(
        self, person_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[Work]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"{_SELECT_ONE} WHERE EXISTS (SELECT 1 FROM works_person_roles r "
                "  WHERE r.works_person_roles_work_id = w.id AND "
                "        r.works_person_roles_person_id = %(cid)s AND "
                "        r.works_person_roles_role_id = %(composer_role)s) "
                "ORDER BY w.id LIMIT %(limit)s OFFSET %(offset)s",
                {**_SELECT_PARAMS, "cid": person_id, "limit": limit, "offset": offset},
            )
            return [_row_to_work(row) for row in await cur.fetchall()]

    async def count(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM works")
            return int((await cur.fetchone())["total"])

    # ------------------------------------------------------------------ listas
    async def replace_tags(self, work_id: int, tags: list[str]) -> None:
        unique = list(dict.fromkeys(t.strip() for t in tags if t and t.strip()))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM work_tag WHERE works_id = %s", (work_id,))
            for tag in unique:
                await cur.execute("INSERT IGNORE INTO tag_work (tag_texto) VALUES (%s)", (tag,))
                await cur.execute("SELECT id FROM tag_work WHERE tag_texto = %s", (tag,))
                row = await cur.fetchone()
                await cur.execute(
                    "INSERT IGNORE INTO work_tag (works_id, tag_id) VALUES (%s, %s)",
                    (work_id, row["id"]),
                )

    async def replace_genres(self, work_id: int, genres: list[str]) -> None:
        unique = list(dict.fromkeys(g.strip() for g in genres if g and g.strip()))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM work_genres WHERE works_id = %s", (work_id,))
            for name in unique:
                gid = await _resolve_genre(cur, name)
                if gid is not None:
                    await cur.execute(
                        "INSERT IGNORE INTO work_genres (works_id, genres_id) VALUES (%s, %s)",
                        (work_id, gid),
                    )

    async def replace_instruments(self, work_id: int, instruments: list[str]) -> None:
        unique = list(dict.fromkeys(i.strip() for i in instruments if i and i.strip()))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM work_instruments WHERE works_id = %s", (work_id,))
            for name in unique:
                iid = await _resolve_instrument(cur, name)
                if iid is not None:
                    await cur.execute(
                        "INSERT IGNORE INTO work_instruments (works_id, instruments_id) "
                        "VALUES (%s, %s)",
                        (work_id, iid),
                    )

    async def replace_parts(self, work_id: int, parts: list[str]) -> None:
        unique = list(dict.fromkeys(p.strip() for p in parts if p and p.strip()))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM work_parts WHERE works_id = %s", (work_id,))
            if unique:
                await cur.executemany(
                    "INSERT INTO work_parts (works_id, work_parts_name) VALUES (%s, %s)",
                    [(work_id, p) for p in unique],
                )

    async def get_tags(self, work_id: int) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT t.tag_texto AS v FROM work_tag wt JOIN tag_work t ON t.id = wt.tag_id "
                "WHERE wt.works_id = %s ORDER BY t.tag_texto",
                (work_id,),
            )
            return [row["v"] for row in await cur.fetchall()]

    async def get_genres(self, work_id: int) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT g.name AS v FROM work_genres wg JOIN genres g ON g.id = wg.genres_id "
                "WHERE wg.works_id = %s ORDER BY g.name",
                (work_id,),
            )
            return [row["v"] for row in await cur.fetchall()]

    async def get_instruments(self, work_id: int) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT i.name_en AS v FROM work_instruments wi "
                "JOIN instruments i ON i.id = wi.instruments_id "
                "WHERE wi.works_id = %s ORDER BY i.name_en",
                (work_id,),
            )
            return [row["v"] for row in await cur.fetchall()]

    async def get_parts(self, work_id: int) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT work_parts_name AS v FROM work_parts WHERE works_id = %s "
                "ORDER BY id",
                (work_id,),
            )
            return [row["v"] for row in await cur.fetchall()]

    async def get_voices(self, work_id: int) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT v.voices_name AS v FROM work_voices wv "
                "JOIN voices v ON v.id = wv.voices_id WHERE wv.works_id = %s "
                "ORDER BY v.voices_sort, v.voices_name",
                (work_id,),
            )
            return [row["v"] for row in await cur.fetchall()]

    async def get_ensembles(self, work_id: int) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT e.ensembles_code AS v FROM work_ensembles we "
                "JOIN ensembles e ON e.id = we.ensembles_id WHERE we.works_id = %s "
                "ORDER BY e.ensembles_code",
                (work_id,),
            )
            return [row["v"] for row in await cur.fetchall()]

    async def get_lists_bulk(self, work_ids: list[int]) -> dict[int, WorkLists]:
        if not work_ids:
            return {}
        result: dict[int, WorkLists] = {wid: WorkLists() for wid in work_ids}
        placeholders = ", ".join(["%s"] * len(work_ids))
        queries = (
            (
                f"SELECT wt.works_id AS wid, t.tag_texto AS v FROM work_tag wt "
                f"JOIN tag_work t ON t.id = wt.tag_id WHERE wt.works_id IN ({placeholders}) "
                "ORDER BY t.tag_texto",
                "tags",
            ),
            (
                f"SELECT wg.works_id AS wid, g.name AS v FROM work_genres wg "
                f"JOIN genres g ON g.id = wg.genres_id WHERE wg.works_id IN ({placeholders}) "
                "ORDER BY g.name",
                "genres",
            ),
            (
                f"SELECT wi.works_id AS wid, i.name_en AS v FROM work_instruments wi "
                f"JOIN instruments i ON i.id = wi.instruments_id "
                f"WHERE wi.works_id IN ({placeholders}) ORDER BY i.name_en",
                "instruments",
            ),
            (
                f"SELECT works_id AS wid, work_parts_name AS v FROM work_parts "
                f"WHERE works_id IN ({placeholders}) ORDER BY id",
                "parts_names",
            ),
            (
                f"SELECT wv.works_id AS wid, v.voices_name AS v FROM work_voices wv "
                f"JOIN voices v ON v.id = wv.voices_id WHERE wv.works_id IN ({placeholders}) "
                "ORDER BY v.voices_sort, v.voices_name",
                "voices",
            ),
            (
                f"SELECT we.works_id AS wid, e.ensembles_code AS v FROM work_ensembles we "
                f"JOIN ensembles e ON e.id = we.ensembles_id "
                f"WHERE we.works_id IN ({placeholders}) ORDER BY e.ensembles_code",
                "ensembles",
            ),
        )
        for sql, attr in queries:
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute(sql, work_ids)
                for row in await cur.fetchall():
                    getattr(result[row["wid"]], attr).append(row["v"])
        return result
