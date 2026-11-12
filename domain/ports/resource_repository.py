"""Puerto de persistencia de Resource V6.

La implementación SQL se añadirá sobre el esquema V6; este puerto mantiene el
dominio independiente del almacenamiento y permite pruebas con dobles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.resource import Resource


class ResourceRepository(ABC):
    @abstractmethod
    async def get(self, resource_id: int) -> Resource | None: ...

    @abstractmethod
    async def list_by_work(self, work_id: int) -> list[Resource]: ...

    @abstractmethod
    async def create(self, resource: Resource) -> Resource: ...

    @abstractmethod
    async def update(self, resource: Resource) -> Resource: ...
