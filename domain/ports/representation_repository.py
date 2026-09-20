from __future__ import annotations

from typing import Protocol

from domain.entities.representation import Representation, Resource


class RepresentationRepository(Protocol):
    async def list_by_work(self, work_id: int) -> list[Representation]: ...

    async def list_by_work_ids(self, work_ids: list[int]) -> list[Representation]: ...

    async def list_resources_by_representation_ids(
        self, representation_ids: list[int]
    ) -> list[Resource]: ...

    async def list_resources_by_work_ids(self, work_ids: list[int]) -> list[Resource]: ...

    async def get_resource(self, resource_id: int) -> Resource | None: ...

    async def get_resource_by_file_id(self, file_id: int) -> Resource | None: ...
