"""Casos de uso de personas (modelo nuevo): listado por rol, ficha y obras.

La API acepta roles por clave (`composer,arranger`); aquí se traducen a ids y se delega en
`SqlPersonQueryRepository`. Lectura pura: no modifica nada.
"""

from __future__ import annotations

from typing import Any

from domain.services.person_roles import parse_role_keys, role_ids_for
from infrastructure.repositories.sql_person_query_repository import SqlPersonQueryRepository


class ListPersons:
    def __init__(self, repo: SqlPersonQueryRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        *,
        role: str | None,
        q: str | None,
        limit: int,
        offset: int,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        keys = parse_role_keys(role)
        items, total = await self._repo.list_persons(
            role_ids_for(keys),
            q=q,
            limit=limit,
            offset=offset,
            include_hidden=include_hidden,
        )
        return {"items": items, "total": total, "roles": list(keys)}


class GetPerson:
    def __init__(self, repo: SqlPersonQueryRepository) -> None:
        self._repo = repo

    async def execute(self, person_id: str) -> dict[str, Any] | None:
        return await self._repo.get_person(person_id)


class GetPersonWorks:
    def __init__(self, repo: SqlPersonQueryRepository) -> None:
        self._repo = repo

    async def execute(
        self, *, person_id: str, role: str | None, limit: int, offset: int
    ) -> dict[str, Any]:
        keys = parse_role_keys(role)
        items, total = await self._repo.works_for_person(
            person_id, role_ids_for(keys), limit=limit, offset=offset
        )
        return {"items": items, "total": total, "roles": list(keys)}
