"""Tests del MVP de atribución asistida por IA (propuesta + revisión humana)."""

from __future__ import annotations

import pytest
from application.use_cases.work_attribution_ai import ProposeWorkAttribution, ReviewProposal
from domain.exceptions import ProposalAssignmentError, ProposalStateError
from domain.ports.work_attribution_ai import AiProposal
from domain.services.composer_names import normalize_composer_name
from infrastructure.ai.errors import AiNotConfiguredError
from infrastructure.ai.fake_attribution_resolver import FakeAttributionResolver
from infrastructure.ai.resolver_factory import NullAttributionResolver


class _FakeRepo:
    def __init__(self) -> None:
        self.proposals: dict[int, dict] = {}
        self.candidates: list[dict] = []
        self.accepted: list[dict] = []
        self.reviews: list[tuple[int, str, str | None, str | None]] = []
        self.normalized_searched: list[str] = []
        self._seq = 0

    async def existing_proposal_for_work(self, work_id: int) -> dict | None:
        return None

    async def work_context(self, work_id: int) -> dict:
        return {"id": work_id, "works_title": "Obra X", "existing_persons": []}

    async def find_person_candidates(self, normalized: str) -> list[dict]:
        self.normalized_searched.append(normalized)
        return self.candidates

    async def save_proposal(self, data: dict) -> int:
        self._seq += 1
        row = dict(data)
        row["id"] = self._seq
        row["status"] = "pending"
        self.proposals[self._seq] = row
        return self._seq

    async def get_proposal(self, proposal_id: int) -> dict | None:
        return self.proposals.get(proposal_id)

    async def accept_proposal(self, **kwargs: object) -> None:
        self.accepted.append(dict(kwargs))
        self.proposals[int(kwargs["proposal_id"])]["status"] = "accepted"

    async def set_review_if_pending(
        self, proposal_id: int, status: str, reviewed_by: str | None, note: str | None
    ) -> None:
        self.reviews.append((proposal_id, status, reviewed_by, note))
        self.proposals[proposal_id]["status"] = status


def _resolver(**kwargs: object) -> FakeAttributionResolver:
    return FakeAttributionResolver(
        proposal=AiProposal(
            resolution=kwargs.get("resolution", "identified"),  # type: ignore[arg-type]
            person_name=kwargs.get("person_name", "Louise Farrenc"),  # type: ignore[arg-type]
            role_name=kwargs.get("role_name", "Arreglista"),  # type: ignore[arg-type]
            confidence=kwargs.get("confidence", 0.96),  # type: ignore[arg-type]
            evidence=[{"type": "source_metadata", "text": "PDMX"}],
        )
    )


async def test_identified_con_una_persona_matched_y_rol_canonico() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(310455)  # type: ignore[arg-type]
    assert saved["resolution"] == "identified"
    assert saved["person_match"] == "matched"
    assert saved["candidate_person_id"] == "p1"
    assert saved["status"] == "pending"
    # El rol lo fija el dominio (Compositor/a), no el modelo (que dijo "Arreglista").
    assert saved["role_id"] == 1
    assert saved["role_name"] == "composer"
    assert repo.accepted == []


async def test_matching_usa_la_normalizacion_canonica() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Béla Bartók"}]
    await ProposeWorkAttribution(repo, _resolver(person_name="Béla Bartók")).execute(1)  # type: ignore[arg-type]
    assert repo.normalized_searched == [normalize_composer_name("Béla Bartók")]
    assert repo.normalized_searched == ["bela bartok"]


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


async def test_anonymous_no_propone_persona() -> None:
    repo = _FakeRepo()
    saved = await ProposeWorkAttribution(
        repo, _resolver(resolution="anonymous", person_name=None, role_name=None)
    ).execute(1)  # type: ignore[arg-type]
    assert saved["resolution"] == "anonymous"
    assert saved["person_match"] == "not_applicable"
    assert saved["candidate_name"] is None
    assert saved["role_id"] is None


async def test_accept_matched_usa_la_via_transaccional() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(310455)  # type: ignore[arg-type]
    result = await ReviewProposal(repo).execute(saved["id"], "accept", reviewed_by="admin-1", note="ok")  # type: ignore[arg-type]
    assert result == {"id": saved["id"], "status": "accepted"}
    assert len(repo.accepted) == 1
    call = repo.accepted[0]
    assert call["work_id"] == 310455
    assert call["person_id"] == "p1"
    assert call["role_id"] == 1
    assert call["created_by"] == "admin-1"
    assert call["proposal_id"] == saved["id"]


async def test_no_se_puede_aceptar_dos_veces() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    review = ReviewProposal(repo)
    await review.execute(saved["id"], "accept", reviewed_by="admin-1")  # type: ignore[arg-type]
    with pytest.raises(ProposalStateError):
        await review.execute(saved["id"], "accept", reviewed_by="admin-1")  # type: ignore[arg-type]
    assert len(repo.accepted) == 1


async def test_no_se_puede_aceptar_una_rechazada() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    review = ReviewProposal(repo)
    await review.execute(saved["id"], "reject", note="tradicional")  # type: ignore[arg-type]
    with pytest.raises(ProposalStateError):
        await review.execute(saved["id"], "accept")  # type: ignore[arg-type]
    assert repo.accepted == []
    assert repo.proposals[saved["id"]]["status"] == "rejected"  # type: ignore[index]


async def test_no_se_puede_revisar_una_aceptada() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    review = ReviewProposal(repo)
    await review.execute(saved["id"], "accept", reviewed_by="admin-1")  # type: ignore[arg-type]
    with pytest.raises(ProposalStateError):
        await review.execute(saved["id"], "uncertain")  # type: ignore[arg-type]
    assert repo.reviews == []


async def test_accept_sin_persona_resuelta_falla() -> None:
    repo = _FakeRepo()
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    with pytest.raises(ProposalAssignmentError):
        await ReviewProposal(repo).execute(saved["id"], "accept")  # type: ignore[arg-type]
    assert repo.accepted == []


async def test_anonymous_no_se_puede_aceptar() -> None:
    repo = _FakeRepo()
    saved = await ProposeWorkAttribution(
        repo, _resolver(resolution="traditional", person_name=None, role_name=None)
    ).execute(1)  # type: ignore[arg-type]
    with pytest.raises(ProposalAssignmentError):
        await ReviewProposal(repo).execute(saved["id"], "accept")  # type: ignore[arg-type]
    assert repo.accepted == []


async def test_reject_y_uncertain_escriben_estado_canonico() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    saved = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    result = await ReviewProposal(repo).execute(saved["id"], "reject", note="tradicional")  # type: ignore[arg-type]
    assert result["status"] == "rejected"
    assert repo.accepted == []


async def test_propuesta_inexistente_falla() -> None:
    repo = _FakeRepo()
    with pytest.raises(LookupError):
        await ReviewProposal(repo).execute(404, "accept")  # type: ignore[arg-type]


async def test_ia_no_configurada_error_claro() -> None:
    repo = _FakeRepo()
    with pytest.raises(AiNotConfiguredError):
        await ProposeWorkAttribution(repo, NullAttributionResolver()).execute(1)  # type: ignore[arg-type]
