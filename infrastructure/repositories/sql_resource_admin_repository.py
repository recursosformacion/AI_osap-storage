from __future__ import annotations

from domain.exceptions import EntityNotFound, InvalidTableCrud

from infrastructure.db.connection import Database

_ALLOWED = {"works_resources_work_id", "works_resources_representation_id",
            "works_resources_type", "works_resources_name", "works_resources_relative_path",
            "works_resources_status", "works_resources_file_id", "works_resources_url",
            "works_resources_archive_id"}


class SqlResourceAdminRepository:
    """CRUD dedicado de `works_resources` (listado con filtros, ficha con obra/representación)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def list(
        self,
        *,
        work_id: int | None = None,
        representation_id: int | None = None,
        type_: str | None = None,
        status: str | None = None,
        has_url: bool | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        where, params = "1=1", []
        if work_id:
            where += " AND r.works_resources_work_id = %s"
            params.append(work_id)
        if representation_id:
            where += " AND r.works_resources_representation_id = %s"
            params.append(representation_id)
        if type_:
            where += " AND r.works_resources_type = %s"
            params.append(type_)
        if status:
            where += " AND r.works_resources_status = %s"
            params.append(status)
        if has_url is not None:
            where += " AND r.works_resources_url IS " + ("NOT NULL" if has_url else "NULL")
        if q:
            where += " AND (r.works_resources_name LIKE %s OR r.works_resources_url LIKE %s)"
            params += [f"%{q}%", f"%{q}%"]
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"SELECT COUNT(*) n FROM works_resources r WHERE {where}", params)
            total = int((await cur.fetchone())["n"])
            await cur.execute(
                "SELECT r.id, r.works_resources_work_id, r.works_resources_representation_id, "
                "r.works_resources_type, r.works_resources_name, r.works_resources_relative_path, "
                "r.works_resources_status, r.works_resources_file_id, r.works_resources_url, "
                "r.works_resources_archive_id "
                f"FROM works_resources r WHERE {where} ORDER BY r.id LIMIT %s OFFSET %s",
                [*params, limit, offset])
            items = [dict(r) for r in await cur.fetchall()]
        return items, total

    async def detail(self, resource_id: int) -> dict:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM works_resources WHERE id = %s", (resource_id,))
            row = await cur.fetchone()
            if row is None:
                raise EntityNotFound("resource", resource_id)
            detail = dict(row)
            await cur.execute(
                "SELECT id, works_title, works_origin FROM works WHERE id = %s",
                (row["works_resources_work_id"],))
            detail["work"] = await cur.fetchone()
            rep_id = row["works_resources_representation_id"]
            detail["representation"] = None
            if rep_id:
                await cur.execute(
                    "SELECT id, representations_origin, representations_origin_id, "
                    "representations_type, representations_license FROM representations WHERE id = %s",
                    (rep_id,))
                detail["representation"] = await cur.fetchone()
        return detail

    async def create(self, data: dict) -> dict:
        cols = [c for c in data if c in _ALLOWED]
        if "works_resources_work_id" not in cols:
            raise InvalidTableCrud("work_id es obligatorio")
        names = ", ".join(f"`{c}`" for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"INSERT INTO works_resources ({names}) VALUES ({placeholders})",
                              [data[c] for c in cols])
            new_id = cur.lastrowid
        return await self.detail(int(new_id))

    async def update(self, resource_id: int, data: dict) -> dict:
        cols = [c for c in data if c in _ALLOWED]
        if not cols:
            raise InvalidTableCrud("no hay columnas válidas para actualizar")
        sets = ", ".join(f"`{c}` = %s" for c in cols)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"UPDATE works_resources SET {sets} WHERE id = %s",
                              [data[c] for c in cols] + [resource_id])
        return await self.detail(resource_id)

    async def delete(self, resource_id: int) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM works_resources WHERE id = %s", (resource_id,))
            return int(cur.rowcount)
