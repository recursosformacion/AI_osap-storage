from __future__ import annotations

from typing import Protocol

from domain.entities.composer_attribution import ComposerAttribution


class ComposerAttributionProvider(Protocol):
    """Proveedor externo de evidencia de atribución (read-only)."""

    async def attribute_many(
        self, titles: list[str]
    ) -> dict[str, list[ComposerAttribution]]:
        """Devuelve atribuciones por título (clave: título normalizado)."""
        ...
