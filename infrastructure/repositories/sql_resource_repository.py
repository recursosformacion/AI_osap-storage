from __future__ import annotations

import json
from typing import Any

from domain.entities.resource import Resource, ResourceKind, ResourceVisibility
from domain.ports.resource_repository import ResourceRepository

from infrastructure.db.connection import Database


def _metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_to_resource(row: dict[str, Any]) -> Resource:
    return Resource(
        id=row["id"],
        work_id=row["work_id"],
        kind=ResourceKind(row.get("kind") or "score"),
        title=row.get("title"),
        source_system=row.get("source_system"),
        external_id=row.get("external_id"),
        external_url=row.get("external_url"),
        license=row.get("license"),
        rights_holder=row.get("rights_holder"),
        is_reference=bool(row.get("is_reference")),
        visibility=ResourceVisibility(row.get("visibility") or "public"),
        metadata=_metadata(row.get("metadata_json")),
        created_by=row.get("created_by"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class SqlResourceRepository(ResourceRepository):
    """Persistencia V6 de Resource sobre `resources`.

    Los File se relacionan por `files.resource_id`; este repositorio no crea ni
    borra ficheros.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, resource_id: int) -> Resource | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
            row = await cur.fetchone()
        return _row_to_resource(row) if row else None

    async def list_by_work(self, work_id: int) -> list[Resource]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM resources WHERE work_id = %s ORDER BY id",
                (work_id,),
            )
            rows = await cur.fetchall()
        return [_row_to_resource(row) for row in rows]

    async def create(self, resource: Resource) -> Resource:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO resources (work_id, kind, title, source_system, external_id, "
                "external_url, license, rights_holder, is_reference, visibility, "
                "metadata_json, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    resource.work_id,
                    resource.kind.value,
                    resource.title,
                    resource.source_system,
                    resource.external_id,
                    resource.external_url,
                    resource.license,
                    resource.rights_holder,
                    int(resource.is_reference),
                    resource.visibility.value,
                    json.dumps(resource.metadata, ensure_ascii=False),
                    resource.created_by,
                ),
            )
            resource.id = cur.lastrowid
            await cur.execute("SELECT * FROM resources WHERE id = %s", (resource.id,))
            row = await cur.fetchone()
        return _row_to_resource(row)

    async def update(self, resource: Resource) -> Resource:
        if resource.id is None:
            raise ValueError("resource.id es obligatorio para actualizar")
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE resources SET work_id = %s, kind = %s, title = %s, "
                "source_system = %s, external_id = %s, external_url = %s, license = %s, "
                "rights_holder = %s, is_reference = %s, visibility = %s, "
                "metadata_json = %s, created_by = %s WHERE id = %s",
                (
                    resource.work_id,
                    resource.kind.value,
                    resource.title,
                    resource.source_system,
                    resource.external_id,
                    resource.external_url,
                    resource.license,
                    resource.rights_holder,
                    int(resource.is_reference),
                    resource.visibility.value,
                    json.dumps(resource.metadata, ensure_ascii=False),
                    resource.created_by,
                    resource.id,
                ),
            )
            await cur.execute("SELECT * FROM resources WHERE id = %s", (resource.id,))
            row = await cur.fetchone()
        return _row_to_resource(row)
