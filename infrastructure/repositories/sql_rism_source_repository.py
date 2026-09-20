from __future__ import annotations

import re
from collections import defaultdict

from domain.entities.rism import RismSource
from domain.ports.rism_source_repository import RismSourceRepository

from infrastructure.db.connection import Database


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"[\s,;.]+", (text or "").lower()) if t]


class SqlRismSourceRepository(RismSourceRepository):
    """Búsqueda local en el corpus RISM (`rism_sources`, read-only)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def _has_fulltext(self, cur: object) -> bool:
        await cur.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*) AS n FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = 'rism_sources' "
            "AND index_name = 'ft_rism_search'"
        )
        row = await cur.fetchone()  # type: ignore[attr-defined]
        return bool(row and int(row.get("n") or 0) > 0)

    async def search(self, query: str, *, limit: int = 50, offset: int = 0) -> list[RismSource]:
        query = (query or "").strip()
        pattern = f"%{query}%"
        tokens = [t for t in _tokenize(query) if len(t) >= 3]
        async with self._db.connection() as conn, conn.cursor() as cur:
            if query and tokens and await self._has_fulltext(cur):
                # `rism_sources` tiene 1,5M de filas: el LIKE con comodín inicial era un full
                # scan (~17s). Con el índice FULLTEXT la búsqueda baja a milisegundos.
                match = " ".join(f"+{token}*" for token in tokens)
                await cur.execute(
                    "SELECT rism_source_id, rism_composer_name, rism_uniform_title, "
                    "       rism_title, rism_reliability, rism_source_type, rism_shelfmark, "
                    "       rism_institution_id, rism_language, rism_has_incipit "
                    "FROM rism_sources "
                    "WHERE MATCH(rism_uniform_title, rism_title, rism_composer_name) "
                    "      AGAINST (%(q)s IN BOOLEAN MODE) "
                    "LIMIT %(limit)s OFFSET %(offset)s",
                    {"q": match, "limit": limit, "offset": offset},
                )
            elif query:
                await cur.execute(
                    "SELECT rism_source_id, rism_composer_name, rism_uniform_title, "
                    "       rism_title, rism_reliability, rism_source_type, rism_shelfmark, "
                    "       rism_institution_id, rism_language, rism_has_incipit "
                    "FROM rism_sources "
                    "WHERE rism_uniform_title LIKE %(p)s OR rism_title LIKE %(p)s "
                    "  OR rism_composer_name LIKE %(p)s "
                    "ORDER BY rism_source_id LIMIT %(limit)s OFFSET %(offset)s",
                    {"p": pattern, "limit": limit, "offset": offset},
                )
            else:
                await cur.execute(
                    "SELECT rism_source_id, rism_composer_name, rism_uniform_title, "
                    "       rism_title, rism_reliability, rism_source_type, rism_shelfmark, "
                    "       rism_institution_id, rism_language, rism_has_incipit "
                    "FROM rism_sources ORDER BY rism_source_id LIMIT %(limit)s OFFSET %(offset)s",
                    {"limit": limit, "offset": offset},
                )
            rows = await cur.fetchall()
            if not rows:
                return []
            source_ids = [row["rism_source_id"] for row in rows]
            placeholders = ", ".join(["%s"] * len(source_ids))
            await cur.execute(
                "SELECT rism_source_id, rism_source_links_url FROM rism_source_links "
                f"WHERE rism_source_id IN ({placeholders}) ORDER BY id",
                source_ids,
            )
            links: dict[str, list[str]] = defaultdict(list)
            for link in await cur.fetchall():
                links[link["rism_source_id"]].append(link["rism_source_links_url"])

        return [
            RismSource(
                source_id=row["rism_source_id"],
                composer_name=row["rism_composer_name"],
                uniform_title=row["rism_uniform_title"],
                title=row["rism_title"],
                reliability=row["rism_reliability"],
                source_type=row["rism_source_type"],
                shelfmark=row["rism_shelfmark"],
                institution_id=row["rism_institution_id"],
                language=row["rism_language"],
                has_incipit=bool(row["rism_has_incipit"]),
                links=tuple(links.get(row["rism_source_id"], [])),
            )
            for row in rows
        ]
