from __future__ import annotations

from domain.exceptions import EntityNotFound, InvalidTableCrud

from infrastructure.db.connection import Database

_ALLOWED = {"representations_works_id", "representations_origin",
            "representations_origin_id", "representations_origin_cpdlno",
            "representations_type", "representations_source_name", "representations_license"}


class SqlRepresentationAdminRepository:
    """CRUD dedicado de `representations` (listado con filtros, ficha con relaciones)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def list(
        self,
        *,
        origin: str | None = None,
        license_: str | None = None,
        works_id: int | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        where, params = "1=1", []
        if origin:
            where += " AND r.representations_origin = %s"
            params.append(origin)
        if license_:
            where += " AND r.representations_license LIKE %s"
            params.append(f"%{license_}%")
        if works_id:
            where += " AND r.representations_works_id = %s"
            params.append(works_id)
        if q:
            where += (" AND (r.representations_origin_id LIKE %s "
                      "OR r.representations_source_name LIKE %s)")
            params += [f"%{q}%", f"%{q}%"]
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"SELECT COUNT(*) n FROM representations r WHERE {where}", params)
            total = int((await cur.fetchone())["n"])
            await cur.execute(
                "SELECT r.id, r.representations_works_id, r.representations_origin, "
                "r.representations_origin_id, r.representations_type, "
                "r.representations_license, r.representations_source_name, "
                "(SELECT COUNT(*) FROM works_resources res "
                "  WHERE res.works_resources_representation_id = r.id) resources, "
                "(SELECT COUNT(*) FROM representation_persons rp "
                "  WHERE rp.representation_persons_representation_id = r.id) editors "
                f"FROM representations r WHERE {where} ORDER BY r.id LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            items = [dict(r) for r in await cur.fetchall()]
        return items, total

    async def detail(self, representation_id: int) -> dict:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM representations WHERE id = %s", (representation_id,))
            row = await cur.fetchone()
            if row is None:
                raise EntityNotFound("representation", representation_id)
            detail = dict(row)
            await cur.execute(
                "SELECT w.id, w.works_title, w.works_origin FROM works w WHERE w.id = %s",
                (row["representations_works_id"],))
            detail["work"] = await cur.fetchone()
            await cur.execute(
                "SELECT id, works_resources_type, works_resources_name, "
                "works_resources_relative_path, works_resources_status, "
                "works_resources_file_id, works_resources_url, works_resources_archive_id "
                "FROM works_resources WHERE works_resources_representation_id = %s ORDER BY id",
                (representation_id,))
            detail["resources"] = [dict(r) for r in await cur.fetchall()]
            await cur.execute(
                "SELECT rp.id, rp.representation_persons_person_id, rp.representation_persons_role_id, "
                "rp.representation_persons_name, p.persons_name "
                "FROM representation_persons rp LEFT JOIN persons p "
                "  ON p.persons_id = rp.representation_persons_person_id "
                "WHERE rp.representation_persons_representation_id = %s ORDER BY rp.id",
                (representation_id,))
            detail["editors"] = [dict(r) for r in await cur.fetchall()]
        return detail

    async def create(self, data: dict) -> dict:
        cols = [c for c in data if c in _ALLOWED]
        if "representations_works_id" not in cols or "representations_origin" not in cols:
            raise InvalidTableCrud("works_id y origin son obligatorios")
        placeholders = ", ".join(["%s"] * len(cols))
        names = ", ".join(f"`{c}`" for c in cols)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"INSERT INTO representations ({names}) VALUES ({placeholders})",
                [data[c] for c in cols])
            new_id = cur.lastrowid
        return await self.detail(int(new_id))

    async def update(self, representation_id: int, data: dict) -> dict:
        cols = [c for c in data if c in _ALLOWED]
        if not cols:
            raise InvalidTableCrud("no hay columnas válidas para actualizar")
        sets = ", ".join(f"`{c}` = %s" for c in cols)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"UPDATE representations SET {sets} WHERE id = %s",
                              [data[c] for c in cols] + [representation_id])
        return await self.detail(representation_id)

    async def delete(self, representation_id: int) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM representations WHERE id = %s", (representation_id,))
            return int(cur.rowcount)
