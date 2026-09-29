"""Resolvedor fake: permite desarrollar y probar todo el MVP sin Gemini."""

from __future__ import annotations

from domain.ports.work_attribution_ai import AiProposal, WorkContext


class FakeAttributionResolver:
    """Devuelve siempre la misma propuesta (configurable) o `unknown` por defecto."""

    def __init__(self, proposal: AiProposal | None = None, model: str = "fake") -> None:
        self.model = model
        self._proposal = proposal

    async def propose(self, context: WorkContext) -> AiProposal:
        if self._proposal is not None:
            return self._proposal
        return AiProposal(
            resolution="unknown",
            person_name=None,
            role_name=None,
            confidence=None,
            evidence=[{"type": "fake", "text": "resolvedor fake sin propuesta"}],
            reason="fake",
            raw={"work_id": context.work_id, "resolution": "unknown"},
        )
