"""Tests del MVP de atribución asistida por IA (propuesta + revisión humana)."""

from __future__ import annotations

import pytest
from application.use_cases.work_attribution_ai import ProposeWorkAttribution, ReviewProposal
from domain.ports.work_attribution_ai import AiProposal
from infrastructure.ai.errors import AiNotConfiguredError
from infrastructure.ai.fake_attribution_resolver import FakeAttributionResolver
from infrastructure.ai.resolver_factory import NullAttributionResolver


class _FakeRepo:
    def __init__(self) -> None:
        self.proposals: dict[int, dict] = {}
        self.assigned: list[tuple[int, str, int]] = []
        self.history: list[dict] = []
        self.candidates: list[dict] = []
        self._seq = 0

    async def existing_proposal_for_work(self, work_id: int) -> dict | None:
        return None

    async def work_context(self, work_id: int) -> dict:
        return {"id": work_id, "works_title": "Obra X", "existing_persons": []}

    async def find_person_candidates(self, name: str, normalized: str) -> list[dict]:
        return self.candidates

    async def role_id_by_name(self, role_name: str) -> int | None:
        return 1 if role_name else None

    async def save_proposal(self, data: dict) -> int:
        self._seq += 1
        row = dict(data)
        row["id"] = self._seq
        row["status"] = "pending"
        self.proposals[self._seq] = row
        return self._seq

    async def get_proposal(self, proposal_id: int) -> dict | None:
        return self.proposals.get(proposal_id)

    async def assign_person_role(self, work_id: int, person_id: str, role_id: int) -> None:
        self.assigned.append((work_id, person_id, role_id))

    async def add_history(self, **kwargs: object) -> None:
        self.history.append(dict(kwargs))

    async def set_review(self, proposal_id: int, status: str, reviewed_by: str | None, note: str | None) -> None:
        self.proposals[proposal_id]["status"] = status


def _resolver(**kwargs: object) -> FakeAttributionResolver:
    return FakeAttributionResolver(
        proposal=AiProposal(
            resolution=kwargs.get("resolution", "identified"),  # type: ignore[arg-type]
            person_name=kwargs.get("person_name", "Louise Farrenc"),  # type: ignore[arg-type]
            role_name=kwargs.get("role_name", "Compositor/a"),  # type: ignore[arg-type]
            confidence=kwargs.get("confidence", 0.96),  # type: ignore[arg-type]
            evidence=[{"type": "source_metadata", "text": "PDMX"}],
        )
    )


async def test_identified_con_una_persona_matched() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(310455)  # type: ignore[arg-type]
    assert saved["resolution"] == "identified"
    assert saved["person_match"] == "matched"
    assert saved["candidate_person_id"] == "p1"
    assert saved["status"] == "pending"


async def test_identified_sin_candidatos_unresolved() -> None:
    repo = _FakeRepo()
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    assert saved["person_match"] == "unresolved"
    assert saved["candidate_person_id"] is None


async def test_identified_con_varios_candidatos_ambiguous() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "J. Smith"}, {"id": "p2", "name": "John Smith"}]
    saved = await ProposeWorkAttribution(repo, _resolver(person_name="J. Smith")).execute(1)  # type: ignore[arg-type]
    assert saved["person_match"] == "ambiguous"


async def test_anonymous_not_applicable() -> None:
    repo = _FakeRepo()
    saved = await ProposeWorkAttribution(
        repo, _resolver(resolution="anonymous", person_name=None, role_name=None)
    ).execute(1)  # type: ignore[arg-type]
    assert saved["resolution"] == "anonymous"
    assert saved["person_match"] == "not_applicable"
    assert saved["candidate_name"] is None


async def test_accept_matched_asigna_y_audita() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    propose = ProposeWorkAttribution(repo, _resolver())
    saved = await propose.execute(310455)  # type: ignore[arg-type]
    result = await ReviewProposal(repo).execute(saved["id"], "accept", reviewed_by="admin", note="ok")  # type: ignore[arg-type]
    assert result["status"] == "accepted"
    assert repo.assigned == [(310455, "p1", 1)]
    assert repo.history and repo.history[0]["operation"] == "assign"
    assert repo.history[0]["source"] == "gemini"
    assert repo.history[0]["proposal_id"] == saved["id"]


async def test_accept_sin_persona_falla() -> None:
    repo = _FakeRepo()
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    with pytest.raises(AiNotConfiguredError):
        await ReviewProposal(repo).execute(saved["id"], "accept")  # type: ignore[arg-type]


async def test_reject_no_asigna_y_queda_registrado() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    result = await ReviewProposal(repo).execute(saved["id"], "reject", note="tradicional")  # type: ignore[arg-type]
    assert result["status"] == "rejected"
    assert repo.assigned == []


async def test_ia_no_configurada_error_claro() -> None:
    repo = _FakeRepo()
    with pytest.raises(AiNotConfiguredError):
        await ProposeWorkAttribution(repo, NullAttributionResolver()).execute(1)  # type: ignore[arg-type]
