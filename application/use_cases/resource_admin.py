from __future__ import annotations

from infrastructure.repositories.sql_resource_admin_repository import SqlResourceAdminRepository

_FIELDS = {
    "work_id": "works_resources_work_id",
    "representation_id": "works_resources_representation_id",
    "type": "works_resources_type",
    "name": "works_resources_name",
    "relative_path": "works_resources_relative_path",
    "status": "works_resources_status",
    "file_id": "works_resources_file_id",
    "url": "works_resources_url",
    "archive_id": "works_resources_archive_id",
}


def _item(row: dict) -> dict:
    return {
        "id": row["id"],
        "work_id": row["works_resources_work_id"],
        "representation_id": row["works_resources_representation_id"],
        "type": row["works_resources_type"],
        "name": row["works_resources_name"],
        "relative_path": row["works_resources_relative_path"],
        "status": row["works_resources_status"],
        "file_id": row["works_resources_file_id"],
        "url": row["works_resources_url"],
        "archive_id": row["works_resources_archive_id"],
    }


def _detail(row: dict) -> dict:
    data = _item(row)
    work = row.get("work") or {}
    rep = row.get("representation")
    data["work"] = {"id": work.get("id"), "title": work.get("works_title"),
                    "origin": work.get("works_origin")}
    data["representation"] = None
    if rep:
        data["representation"] = {
            "id": rep["id"], "origin": rep["representations_origin"],
            "origin_id": rep["representations_origin_id"],
            "type": rep["representations_type"], "license": rep["representations_license"],
        }
    return data


def _payload(data: dict) -> dict:
    return {column: data[field] for field, column in _FIELDS.items() if field in data}


class ResourceAdminCrud:
    def __init__(self, repo: SqlResourceAdminRepository) -> None:
        self._repo = repo

    async def list(self, **filters) -> tuple[list[dict], int]:
        items, total = await self._repo.list(**filters)
        return [_item(r) for r in items], total

    async def detail(self, resource_id: int) -> dict:
        return _detail(await self._repo.detail(resource_id))

    async def create(self, data: dict) -> dict:
        return _detail(await self._repo.create(_payload(data)))

    async def update(self, resource_id: int, data: dict) -> dict:
        return _detail(await self._repo.update(resource_id, _payload(data)))

    async def delete(self, resource_id: int) -> int:
        return await self._repo.delete(resource_id)
