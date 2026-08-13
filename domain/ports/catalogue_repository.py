from __future__ import annotations

from typing import Protocol

from domain.entities.catalogue import Catalogue


class CatalogueRepository(Protocol):
    """Acceso a los catálogos musicales por compositor."""

    async def get_by_prefix(self, prefix: str) -> list[Catalogue]:
        """Catálogos cuya sigla es `prefix` (puede haber varios compositores)."""

    async def get_by_composer(self, composer: str) -> list[Catalogue]:
        """Catálogos de un compositor (coincidencia por nombre normalizado)."""

    async def list_all(self, *, limit: int, offset: int) -> list[Catalogue]: ...

    async def seed(self, catalogues: list[Catalogue]) -> int:
        """Siembra la tabla de forma idempotente. Devuelve cuántas se insertaron."""
