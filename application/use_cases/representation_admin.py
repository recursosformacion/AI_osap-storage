from __future__ import annotations

from infrastructure.repositories.sql_representation_admin_repository import (
    SqlRepresentationAdminRepository,
)

_FIELDS = {
    "works_id": "representations_works_id",
    "origin": "representations_origin",
    "origin_id": "representations_origin_id",
    "cpdlno": "representations_origin_cpdlno",
    "type": "representations_type",
    "license": "representations_license",
    "source_name": "representations_source_name",
}


def _list_item(row: dict) -> dict:
    return {
        "id": row["id"],
        "works_id": row["representations_works_id"],
        "origin": row["representations_origin"],
        "origin_id": row["representations_origin_id"],
        "type": row["representations_type"],
        "license": row["representations_license"],
        "source_name": row["representations_source_name"],
        "resources": row["resources"],
        "editors": row["editors"],
    }


def _detail(row: dict) -> dict:
    work = row.get("work") or {}
    return {
        "id": row["id"],
        "works_id": row["representations_works_id"],
        "origin": row["representations_origin"],
        "origin_id": row["representations_origin_id"],
        "cpdlno": row["representations_origin_cpdlno"],
        "type": row["representations_type"],
        "license": row["representations_license"],
        "source_name": row["representations_source_name"],
        "work": {"id": work.get("id"), "title": work.get("works_title"),
                 "origin": work.get("works_origin")},
        "resources": [
            {"id": r["id"], "type": r["works_resources_type"], "name": r["works_resources_name"],
             "relative_path": r["works_resources_relative_path"], "status": r["works_resources_status"],
             "file_id": r["works_resources_file_id"], "url": r["works_resources_url"],
             "archive_id": r["works_resources_archive_id"]}
            for r in row.get("resources", [])
        ],
        "editors": [
            {"id": e["id"], "person_id": e["representation_persons_person_id"],
             "role_id": e["representation_persons_role_id"], "name": e["representation_persons_name"],
             "person_name": e.get("persons_name")}
            for e in row.get("editors", [])
        ],
    }


def _payload(data: dict) -> dict:
    return {column: data[field] for field, column in _FIELDS.items() if field in data}


class RepresentationAdminCrud:
    def __init__(self, repo: SqlRepresentationAdminRepository) -> None:
        self._repo = repo

    async def list(self, **filters) -> tuple[list[dict], int]:
        items, total = await self._repo.list(**filters)
        return [_list_item(r) for r in items], total

    async def detail(self, representation_id: int) -> dict:
        return _detail(await self._repo.detail(representation_id))

    async def create(self, data: dict) -> dict:
        return _detail(await self._repo.create(_payload(data)))

    async def update(self, representation_id: int, data: dict) -> dict:
        return _detail(await self._repo.update(representation_id, _payload(data)))

    async def delete(self, representation_id: int) -> int:
        return await self._repo.delete(representation_id)
