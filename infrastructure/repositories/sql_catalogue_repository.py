from __future__ import annotations

from domain.entities.catalogue import Catalogue
from domain.ports.catalogue_repository import CatalogueRepository
from domain.services.composer_names import normalize_composer_name

from infrastructure.db.connection import Database

# El esquema nuevo usa `catalog` como catálogo de **extracción** (id + patrón regex
# + plantilla de formato) en lugar del antiguo `catalogues` (prefix/composer/creator).
# Adaptador provisional: se mapea `catalog_id` -> prefix y `catalog_format_template`
# -> ordering_criterion. El rediseño de la API de catálogos queda para la fase 4.


def _row_to_catalogue(row: dict) -> Catalogue:
    return Catalogue(
        id=row["id"],
        prefix=row["catalog_id"],
        composer="",
        catalogue_name=row["catalog_name"],
        creator="",
        ordering_criterion=row.get("catalog_format_template") or "",
        created_at=row.get("created_at"),
    )


class SqlCatalogueRepository(CatalogueRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_by_prefix(self, prefix: str) -> list[Catalogue]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM catalog WHERE catalog_id = %s ORDER BY catalog_name",
                (prefix,),
            )
            return [_row_to_catalogue(row) for row in await cur.fetchall()]

    async def get_by_composer(self, composer: str) -> list[Catalogue]:
        # El catálogo nuevo no tiene campo `composer`.
        if not normalize_composer_name(composer):
            return []
        return []

    async def list_all(self, *, limit: int, offset: int) -> list[Catalogue]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM catalog ORDER BY catalog_id, catalog_name LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_catalogue(row) for row in await cur.fetchall()]

    async def seed(self, catalogues: list[Catalogue]) -> int:
        inserted = 0
        for c in catalogues:
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM catalog WHERE catalog_id = %s AND catalog_name = %s LIMIT 1",
                    (c.prefix, c.catalogue_name),
                )
                if await cur.fetchone() is None:
                    await cur.execute(
                        "INSERT INTO catalog "
                        "(catalog_id, catalog_name, catalog_regex_pattern, "
                        " catalog_format_template, catalog_description) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (c.prefix, c.catalogue_name, None,
                         c.ordering_criterion or None, c.creator or None),
                    )
                    inserted += 1
        return inserted
