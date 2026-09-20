from __future__ import annotations

from collections import defaultdict

from domain.entities.rism import RismSource
from domain.ports.rism_source_repository import RismSourceRepository

from infrastructure.db.connection import Database


class SqlRismSourceRepository(RismSourceRepository):
    """Búsqueda local en el corpus RISM (`rism_sources`, read-only)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def search(self, query: str, *, limit: int = 50, offset: int = 0) -> list[RismSource]:
        query = (query or "").strip()
        pattern = f"%{query}%"
        async with self._db.connection() as conn, conn.cursor() as cur:
            if query:
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
