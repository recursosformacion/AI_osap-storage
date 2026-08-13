from __future__ import annotations

from domain.entities.catalogue import Catalogue, catalogue_prefix
from domain.ports.catalogue_repository import CatalogueRepository


class CatalogueQueries:
    """Consultas de catálogos musicales."""

    def __init__(self, catalogues: CatalogueRepository) -> None:
        self._catalogues = catalogues

    async def by_prefix(self, prefix: str) -> list[Catalogue]:
        return await self._catalogues.get_by_prefix(prefix.strip())

    async def by_composer(self, composer: str) -> list[Catalogue]:
        return await self._catalogues.get_by_composer(composer.strip())

    async def list(self, *, limit: int, offset: int) -> list[Catalogue]:
        return await self._catalogues.list_all(limit=limit, offset=offset)

    async def composer_from_reference(self, reference: str | None) -> str | None:
        """Devuelve el compositor inferido del catálogo de una referencia de obra.

        Extrae el prefijo (p. ej. "K. 15h" -> "K") y, si el prefijo identifica a un
        único catálogo, devuelve su compositor (ayuda a la limpieza de compositores).
        Si el prefijo es ambiguo (varios compositores) o no se encuentra, devuelve None.
        """
        prefix = catalogue_prefix(reference)
        if not prefix:
            return None
        matches = await self._catalogues.get_by_prefix(prefix)
        if len(matches) == 1:
            return matches[0].composer
        return None
