from __future__ import annotations

from domain.entities.representation import Representation, Resource
from domain.ports.representation_repository import RepresentationRepository

from infrastructure.db.connection import Database


def _row_to_representation(row: dict) -> Representation:
    return Representation(
        id=row["id"],
        works_id=row["representations_works_id"],
        origin=row["representations_origin"],
        origin_id=row["representations_origin_id"],
        origin_cpdlno=row["representations_origin_cpdlno"],
        type=row["representations_type"],
        source_name=row["representations_source_name"],
        license=row["representations_license"],
        created_at=row["representations_created_at"],
        updated_at=row["representations_updated_at"],
    )


def _row_to_resource(row: dict) -> Resource:
    return Resource(
        id=row["id"],
        representation_id=row["works_resources_representation_id"],
        work_id=row["works_resources_work_id"],
        type=row["works_resources_type"],
        name=row["works_resources_name"],
        relative_path=row["works_resources_relative_path"],
        status=row["works_resources_status"],
        file_id=row["works_resources_file_id"],
        url=row["works_resources_url"],
        archive_id=row["works_resources_archive_id"],
        created_at=row["works_resources_created_at"],
        updated_at=row["works_resources_updated_at"],
    )


class SqlRepresentationRepository(RepresentationRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_by_work(self, work_id: int) -> list[Representation]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM representations WHERE representations_works_id = %s "
                "ORDER BY representations_origin, id",
                (work_id,),
            )
            return [_row_to_representation(row) for row in await cur.fetchall()]

    async def list_by_work_ids(self, work_ids: list[int]) -> list[Representation]:
        if not work_ids:
            return []
        placeholders = ", ".join(["%s"] * len(work_ids))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM representations "
                f"WHERE representations_works_id IN ({placeholders}) "
                "ORDER BY representations_works_id, representations_origin, id",
                work_ids,
            )
            return [_row_to_representation(row) for row in await cur.fetchall()]

    async def list_resources_by_representation_ids(
        self, representation_ids: list[int]
    ) -> list[Resource]:
        if not representation_ids:
            return []
        placeholders = ", ".join(["%s"] * len(representation_ids))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM works_resources "
                f"WHERE works_resources_representation_id IN ({placeholders}) "
                "ORDER BY works_resources_representation_id, id",
                representation_ids,
            )
            return [_row_to_resource(row) for row in await cur.fetchall()]

    async def list_resources_by_work_ids(self, work_ids: list[int]) -> list[Resource]:
        if not work_ids:
            return []
        placeholders = ", ".join(["%s"] * len(work_ids))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM works_resources "
                f"WHERE works_resources_work_id IN ({placeholders}) "
                "ORDER BY works_resources_work_id, id",
                work_ids,
            )
            return [_row_to_resource(row) for row in await cur.fetchall()]

    async def get_resource(self, resource_id: int) -> Resource | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM works_resources WHERE id = %s", (resource_id,))
            row = await cur.fetchone()
            return _row_to_resource(row) if row else None

    async def get_resource_by_file_id(self, file_id: int) -> Resource | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM works_resources WHERE works_resources_file_id = %s "
                "ORDER BY id LIMIT 1",
                (file_id,),
            )
            row = await cur.fetchone()
            return _row_to_resource(row) if row else None
