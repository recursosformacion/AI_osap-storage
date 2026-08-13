from __future__ import annotations

from domain.entities.catalogue import Catalogue
from domain.ports.catalogue_repository import CatalogueRepository
from domain.services.composer_names import normalize_composer_name

from infrastructure.db.connection import Database


def _row_to_catalogue(row: dict) -> Catalogue:
    return Catalogue(
        id=row["id"],
        prefix=row["prefix"],
        composer=row["composer"],
        catalogue_name=row["catalogue_name"],
        creator=row["creator"],
        ordering_criterion=row["ordering_criterion"],
        created_at=row["created_at"],
    )


class SqlCatalogueRepository(CatalogueRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_by_prefix(self, prefix: str) -> list[Catalogue]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM catalogues WHERE prefix = %s ORDER BY composer",
                (prefix,),
            )
            return [_row_to_catalogue(row) for row in await cur.fetchall()]

    async def get_by_composer(self, composer: str) -> list[Catalogue]:
        norm = normalize_composer_name(composer)
        if not norm:
            return []
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM catalogues ORDER BY composer", ()
            )
            rows = await cur.fetchall()
        out: list[Catalogue] = []
        for row in rows:
            item = _row_to_catalogue(row)
            if norm in normalize_composer_name(item.composer):
                out.append(item)
        return out

    async def list_all(self, *, limit: int, offset: int) -> list[Catalogue]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM catalogues ORDER BY composer, prefix LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_catalogue(row) for row in await cur.fetchall()]

    async def seed(self, catalogues: list[Catalogue]) -> int:
        inserted = 0
        for c in catalogues:
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM catalogues WHERE prefix = %s AND composer = %s "
                    "AND catalogue_name = %s LIMIT 1",
                    (c.prefix, c.composer, c.catalogue_name),
                )
                if await cur.fetchone() is None:
                    await cur.execute(
                        "INSERT INTO catalogues "
                        "(prefix, composer, catalogue_name, creator, ordering_criterion) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (c.prefix, c.composer, c.catalogue_name, c.creator, c.ordering_criterion),
                    )
                    inserted += 1
        return inserted
