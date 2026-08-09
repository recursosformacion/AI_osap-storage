from __future__ import annotations

from domain.ports.composer_repository import ComposerRepository
from domain.services.composer_names import normalize_composer_name


class ComposerResolver:
    """Resuelve un nombre de compositor procedente de un proveedor a su identidad canónica.

    Almacena la forma normalizada de cada nombre para resolverlo contra
    `composer_aliases` y devolver `(composer_id, nombre canónico)` o `None`.
    La normalización y la consulta por lotes evitan llamadas N+1.
    """

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def resolve(self, name: str | None) -> tuple[str, str] | None:
        normalized = normalize_composer_name(name)
        if not normalized:
            return None
        return await self._composers.resolve_by_normalized(normalized)

    async def resolve_many(
        self, names: list[str | None]
    ) -> dict[str | None, tuple[str, str] | None]:
        """Resuelve un conjunto de nombres en una única consulta.

        Devuelve un mapa con la misma clave original (el nombre tal cual) para que
        el llamante pueda consultar directamente `result[work.composer]`.
        """
        if not names:
            return {}

        distinct: dict[str, str] = {}
        for name in names:
            if name is None:
                continue
            normalized = normalize_composer_name(name)
            if normalized and normalized not in distinct:
                distinct[normalized] = name

        resolved = await self._composers.resolve_many_by_normalized(list(distinct))

        result: dict[str | None, tuple[str, str] | None] = {}
        for name in names:
            normalized = normalize_composer_name(name)
            result[name] = resolved.get(normalized) if normalized else None
        return result
