from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from domain.entities.composer import Composer
from domain.ports.composer_repository import ComposerRepository
from domain.services.composer_names import normalize_composer_name
from domain.services.composer_quality import clean_composer_name, extract_composer_name

_EMPTY_MARKERS = {"na", "n/a", "nan", "null", "none", "unknown", "anon", "anon.", "anonymous", "-"}


@dataclass(frozen=True)
class PopulateComposersResult:
    composers: int
    aliases: int
    reused: int


class PopulateComposers:
    """Puebla `composers` / `composer_aliases` a partir de nombres de compositor de origen.

    Proceso admin idempotente:
    - agrupa los nombres por su forma normalizada (`normalized_alias`);
    - para cada grupo, elige un nombre canónico determinista (el más frecuente, con
      desempate al más largo) y crea el compositor con un UUID;
    - registra el alias canónico (su `normalized_alias` = clave del grupo);
    - si el grupo ya tiene compositor, lo reutiliza (no duplica).

    No aplica ningún algoritmo de "mejor compositor" ni fusiona formas normalizadas
    distintas: dos grupos distintos permanecen como compositores separados hasta que
    la administración los fusione explícitamente.
    """

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(
        self, names: Iterable[str], *, provider: str | None = None
    ) -> PopulateComposersResult:
        groups: dict[str, dict[str, int]] = {}
        extract_cache: dict[str, str | None] = {}
        for name in names:
            raw = (name or "").strip()
            if not raw or raw.lower() in _EMPTY_MARKERS:
                continue
            # Caché por nombre bruto: evita repetir NER para el mismo texto (los nombres
            # aparecen muchas veces en el índice, pero las extracciones son pocas y costosas).
            if raw not in extract_cache:
                extract_cache[raw] = extract_composer_name(raw)
            extracted = extract_cache[raw]
            if not extracted:
                continue
            normalized = normalize_composer_name(extracted)
            if not normalized:
                continue
            spellings = groups.setdefault(normalized, {})
            spellings[raw] = spellings.get(raw, 0) + 1

        created = 0
        aliases = 0
        reused = 0
        for normalized, spellings in groups.items():
            raw_canonical = self._pick_canonical(spellings)
            canonical = extract_composer_name(raw_canonical) or clean_composer_name(raw_canonical)
            existing = await self._composers.resolve_by_normalized(normalized)
            if existing is not None:
                reused += 1
                continue
            composer = await self._composers.create(Composer(id="", name=canonical))
            await self._composers.add_alias(
                composer.id, canonical, normalize_composer_name(canonical)
            )
            if provider:
                await self._composers.add_creation_evidence(
                    composer.id,
                    extracted_author=canonical,
                    provider=provider,
                    resource_reference=canonical,
                )
            created += 1
            aliases += 1

        return PopulateComposersResult(composers=created, aliases=aliases, reused=reused)

    @staticmethod
    def _pick_canonical(spellings: dict[str, int]) -> str:
        # Más frecuente; desempate por el más largo; luego lexicográfico.
        return min(spellings.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0]
