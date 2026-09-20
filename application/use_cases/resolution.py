from __future__ import annotations

from domain.entities.composer_attribution import (
    STATE_AMBIGUOUS,
    STATE_INFERRED,
    STATE_RESOLVED,
    STATE_UNCLASSIFIED,
    ComposerAttribution,
)
from domain.entities.resolution import ResolutionResult, ResourceEvidence
from domain.exceptions import EntityNotFound
from domain.ports.composer_attribution_provider import ComposerAttributionProvider
from domain.ports.resolution_source import ResolutionSource
from domain.services.composer_names import normalize_composer_name
from domain.services.grouping_resolver import resolve

_STATE_ORDER = {
    STATE_RESOLVED: 0,
    STATE_INFERRED: 1,
    STATE_AMBIGUOUS: 2,
    STATE_UNCLASSIFIED: 3,
}


def _best_attribution(matches: list[ComposerAttribution]) -> ComposerAttribution | None:
    usable = [a for a in matches if a.person_id]
    if not usable:
        return None
    best_rank = min(_STATE_ORDER.get(a.state, 3) for a in usable)
    best = [a for a in usable if _STATE_ORDER.get(a.state, 3) == best_rank]
    if len({a.person_id for a in best}) > 1:
        return ComposerAttribution(
            person_id=None,
            person_name=None,
            state=STATE_AMBIGUOUS,
            source=best[0].source,
            matched_title=best[0].matched_title,
        )
    return best[0]


class ResolveWorkGrouping:
    """Resuelve Representation/Work para una obra: agrupación inferida, solo lectura.

    Puede usar un `ComposerAttributionProvider` (p. ej. RISM) para aportar identidad de
    compositor a obras sin compositor resuelto, sin persistir nada.
    """

    def __init__(
        self,
        source: ResolutionSource,
        attributions_provider: ComposerAttributionProvider | None = None,
    ) -> None:
        self._source = source
        self._attributions = attributions_provider

    async def execute(self, work_id: int, *, candidate_limit: int = 50) -> ResolutionResult:
        evidences = await self._source.load(work_id, candidate_limit=candidate_limit)
        if not evidences:
            raise EntityNotFound("work", work_id)
        attributions = await self._load_attributions(evidences)
        return resolve(evidences, attributions)

    async def _load_attributions(
        self, evidences: list[ResourceEvidence]
    ) -> dict[int, ComposerAttribution]:
        if self._attributions is None:
            return {}
        titles = sorted({e.title for e in evidences if not e.composer_id and e.title})
        if not titles:
            return {}
        by_title = await self._attributions.attribute_many(titles)
        out: dict[int, ComposerAttribution] = {}
        for evidence in evidences:
            if evidence.composer_id or not evidence.title:
                continue
            matches = by_title.get(normalize_composer_name(evidence.title))
            if not matches:
                continue
            best = _best_attribution(matches)
            if best is not None:
                out[evidence.work_id] = best
        return out
