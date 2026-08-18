"""Ingestor JSON → `authority_identifiers` (deliberadamente pequeño).

Solo lee los snapshots JSON (`data/authority/*.json`), valida, convierte al modelo
`AuthorityIdentifier` y hace upsert vía `AuthorityIdentifierRepository`. Idempotente:
ejecutarlo dos veces deja exactamente el mismo estado.

NO hace aquí: consultas a Wikidata/VIAF, resolución, fuzzy matching, decisión de cuál
identificador es correcto, lógica CISAC, canonical_composer ni confidence. Eso pertenece
al enrichment/provider pipeline. El ingestor solo materializa lo ya obtenido.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities.authority_identifier import (
    AuthorityEntityType,
    AuthorityIdentifier,
    AuthorityScheme,
)
from domain.ports.authority_identifier_repository import AuthorityIdentifierRepository

_VALID_TYPES = frozenset({AuthorityEntityType.WORK, AuthorityEntityType.COMPOSER})
_VALID_SCHEMES = frozenset(
    {
        AuthorityScheme.WIKIDATA,
        AuthorityScheme.ISNI,
        AuthorityScheme.VIAF,
        AuthorityScheme.LCCN,
        AuthorityScheme.MUSICBRAINZ,
        AuthorityScheme.ISWC,
        AuthorityScheme.IPI,
    }
)

# JSON attribute → scheme
_COMPOSER_SCHEMES = (
    ("isni", AuthorityScheme.ISNI),
    ("ipi", AuthorityScheme.IPI),
    ("wikidata", AuthorityScheme.WIKIDATA),
    ("viaf", AuthorityScheme.VIAF),
    ("musicbrainz", AuthorityScheme.MUSICBRAINZ),
    ("lccn", AuthorityScheme.LCCN),
)
_WORK_SCHEMES = (
    ("iswc", AuthorityScheme.ISWC),
    ("wikidata_work", AuthorityScheme.WIKIDATA),
    ("musicbrainz_work", AuthorityScheme.MUSICBRAINZ),
)


@dataclass
class IngestResult:
    inserted: int = 0
    updated: int = 0
    ignored: int = 0
    invalid: int = 0
    conflict: int = 0
    invalid_errors: list[str] = field(default_factory=list)


class AuthoritySnapshotIngestor:
    """Materializa snapshots JSON en `authority_identifiers`. Idempotente."""

    def __init__(self, repo: AuthorityIdentifierRepository) -> None:
        self._repo = repo

    async def ingest_composers(self, composers: dict[str, dict]) -> IngestResult:
        return await self._ingest(composers, AuthorityEntityType.COMPOSER, _COMPOSER_SCHEMES)

    async def ingest_works(self, works: dict[str, dict]) -> IngestResult:
        return await self._ingest(works, AuthorityEntityType.WORK, _WORK_SCHEMES)

    async def _ingest(
        self, records: dict[str, dict], entity_type: str, schemes: tuple[tuple[str, str], ...]
    ) -> IngestResult:
        result = IngestResult()
        seen: dict[tuple[str, str], str] = {}  # (scheme, value) -> primer entity_id
        for entity_id, rec in records.items():
            entity_id = str(entity_id or "").strip()
            if not entity_id or not isinstance(rec, dict):
                result.invalid += 1
                result.invalid_errors.append(f"{entity_type}/{entity_id}: registro inválido")
                continue
            if entity_type not in _VALID_TYPES:
                result.invalid += 1
                result.invalid_errors.append(f"{entity_type}/{entity_id}: entity_type inválido")
                continue
            source = str(rec.get("source") or "json")
            for attr, scheme in schemes:
                raw = rec.get(attr)
                if raw is None:
                    continue
                value = str(raw).strip()
                if not value:
                    continue
                if scheme not in _VALID_SCHEMES:
                    result.invalid += 1
                    result.invalid_errors.append(f"{entity_type}/{entity_id}/{scheme}: scheme inválido")
                    continue
                # Conflicto de autoridad (mismo scheme+value en otra entidad) → informativo,
                # NO se impone unicidad: aún no decidimos cómo tratar conflictos.
                key = (scheme, value)
                if key in seen and seen[key] != entity_id:
                    result.conflict += 1
                else:
                    seen[key] = entity_id

                existing = await self._repo.get(entity_type, entity_id, scheme)
                if existing is None:
                    await self._repo.upsert(
                        AuthorityIdentifier(
                            entity_type=entity_type, entity_id=entity_id,
                            scheme=scheme, value=value, source=source,
                        )
                    )
                    result.inserted += 1
                elif existing.value == value:
                    result.ignored += 1
                else:
                    await self._repo.upsert(
                        AuthorityIdentifier(
                            entity_type=entity_type, entity_id=entity_id,
                            scheme=scheme, value=value, source=source,
                        )
                    )
                    result.updated += 1
        return result
