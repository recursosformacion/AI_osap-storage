from __future__ import annotations

from domain.entities.composer import Composer
from domain.exceptions import DuplicateComposerAlias
from domain.ports.composer_repository import ComposerRepository
from domain.services.composer_names import normalize_composer_name
from infrastructure.services.musicbrainz_client import MusicBrainzClient


class EnrichComposersMusicBrainz:
    """Enriquece compositores con MusicBrainz (validate + canonicalize + merge).

    Para cada compositor de un lote (por defecto los `not_reviewed`):
    - busca el artista en MusicBrainz (exigiendo `type == Person`);
    - si hay match, obtiene el nombre canónico de MB;
    - si ya existe otro compositor con ese nombre canónico, **fusiona** el actual en él
      (el merge reasigna automáticamente aliases, obras y evidencia al compositor destino);
    - si no existe, renombra el actual al nombre canónico de MB, añade sus alias y guarda
      el MBID, y lo marca `correct`.
    """

    def __init__(self, composers: ComposerRepository, mb: MusicBrainzClient) -> None:
        self._composers = composers
        self._mb = mb

    async def execute(self, *, limit: int = 50) -> dict[str, int]:
        counts = {"checked": 0, "matched": 0, "merged": 0, "renamed": 0, "no_match": 0}
        pending = await self._composers.list_pending_review(limit=limit, offset=0)
        for item in pending:
            counts["checked"] += 1
            artist = await self._best_person(item.name)
            if artist is None:
                counts["no_match"] += 1
                continue

            counts["matched"] += 1
            canonical = (artist.get("name") or "").strip()
            if not canonical:
                counts["no_match"] += 1
                continue

            existing = await self._find_by_canonical(canonical)
            if existing is not None and existing.id != item.id:
                # Fusionar en el canónico existente (reasigna alias, obras y evidencia).
                await self._composers.merge(existing.id, [item.id])
                await self._composers.set_musicbrainz_id(existing.id, artist.get("id"))
                await self._composers.set_review_status(existing.id, "correct")
                counts["merged"] += 1
            else:
                await self._composers.rename_composer(item.id, canonical)
                await self._composers.set_musicbrainz_id(item.id, artist.get("id"))
                await self._add_aliases(item.id, artist.get("aliases", []))
                await self._composers.set_review_status(item.id, "correct")
                counts["renamed"] += 1
        return counts

    async def _best_person(self, name: str) -> dict | None:
        try:
            artists = await self._mb.search_artists(name)
        except Exception:
            return None
        persons = [a for a in artists if (a.get("type") or "").lower() == "person"]
        if not persons:
            return None
        target_norm = normalize_composer_name(name)
        for a in persons:
            if normalize_composer_name(a.get("name")) == target_norm:
                return a
        return max(persons, key=lambda a: a.get("score", 0))

    async def _find_by_canonical(self, canonical: str) -> Composer | None:
        existing = await self._composers.get_by_name(canonical)
        if existing is None:
            resolved = await self._composers.resolve_by_normalized(normalize_composer_name(canonical))
            if resolved is not None:
                existing = await self._composers.get_by_id(resolved[0])
        return existing

    async def _add_aliases(self, composer_id: str, aliases: list[dict]) -> None:
        for alias in aliases:
            name = (alias.get("name") or "").strip()
            if not name:
                continue
            try:
                await self._composers.add_alias(composer_id, name, normalize_composer_name(name))
            except DuplicateComposerAlias:
                continue
