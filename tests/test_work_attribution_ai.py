"""Tests del MVP de atribución asistida por IA (propuesta, re-propuesta y revisión humana)."""

from __future__ import annotations

from typing import Any

import pytest
from application.use_cases.work_attribution_ai import ProposeWorkAttribution, ReviewProposal
from domain.exceptions import ProposalAssignmentError, ProposalStateError
from domain.ports.work_attribution_ai import AiProposal, WorkContext
from domain.services.composer_names import normalize_composer_name
from infrastructure.ai.errors import AiNotConfiguredError, AiUpstreamError
from infrastructure.ai.fake_attribution_resolver import FakeAttributionResolver
from infrastructure.ai.resolver_factory import NullAttributionResolver


class _CapturingResolver(FakeAttributionResolver):
    """Fake que además guarda el contexto enviado (para comprobar el prompt)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.contexts: list[WorkContext] = []

    async def propose(self, context: WorkContext) -> AiProposal:
        self.contexts.append(context)
        return await super().propose(context)


class _FakeRepo:
    def __init__(self) -> None:
        self.proposals: dict[int, dict] = {}
        self.candidates: list[dict] = []
        self.accepted: list[dict] = []
        self.reviews: list[tuple[int, str, str | None, str | None]] = []
        self.normalized_searched: list[str] = []
        self.latest: dict | None = None
        self.genre: str | None = None
        self._seq = 0

    async def latest_proposal_for_work(self, work_id: int) -> dict | None:
        return self.latest

    async def work_context(self, work_id: int) -> dict:
        return {"id": work_id, "works_title": "Obra X", "existing_persons": []}

    async def work_genres(self, work_id: int) -> str | None:
        return self.genre

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


def _resolver(**kwargs: object) -> _CapturingResolver:
    return _CapturingResolver(
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
    result = await ProposeWorkAttribution(repo, _resolver()).execute(310455)  # type: ignore[arg-type]
    saved = result["proposal"]
    assert result["reused"] is False
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


async def test_contexto_incluye_genero() -> None:
    repo = _FakeRepo()
    repo.genre = "Canción, Motete"
    resolver = _resolver()
    await ProposeWorkAttribution(repo, resolver).execute(1)  # type: ignore[arg-type]
    assert resolver.contexts[0].genre == "Canción, Motete"


async def test_identified_sin_candidatos_unresolved() -> None:
    repo = _FakeRepo()
    result = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    assert result["proposal"]["person_match"] == "unresolved"
    assert result["proposal"]["candidate_person_id"] is None


async def test_identified_con_varios_candidatos_ambiguous() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "J. Smith"}, {"id": "p2", "name": "John Smith"}]
    result = await ProposeWorkAttribution(repo, _resolver(person_name="J. Smith")).execute(1)  # type: ignore[arg-type]
    assert result["proposal"]["person_match"] == "ambiguous"


async def test_anonymous_no_propone_persona() -> None:
    repo = _FakeRepo()
    result = await ProposeWorkAttribution(
        repo, _resolver(resolution="anonymous", person_name=None, role_name=None)
    ).execute(1)  # type: ignore[arg-type]
    saved = result["proposal"]
    assert saved["resolution"] == "anonymous"
    assert saved["person_match"] == "not_applicable"
    assert saved["candidate_name"] is None
    assert saved["role_id"] is None


async def test_reutiliza_la_ultima_propuesta_sin_llamar_a_la_ia() -> None:
    for status in ("pending", "accepted", "rejected", "uncertain"):
        repo = _FakeRepo()
        repo.latest = {"id": 9, "work_id": 1, "status": status}
        resolver = _resolver()
        result = await ProposeWorkAttribution(repo, resolver).execute(1)  # type: ignore[arg-type]
        assert result["reused"] is True
        assert result["proposal"]["status"] == status
        assert resolver.contexts == []  # no se consultó a la IA
        assert repo.proposals == {}  # no se guardó nada nuevo


async def test_force_reconsulta_y_crea_propuesta_nueva() -> None:
    repo = _FakeRepo()
    repo.latest = {"id": 9, "work_id": 1, "status": "uncertain"}
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    resolver = _resolver()
    result = await ProposeWorkAttribution(repo, resolver).execute(1, force=True)  # type: ignore[arg-type]
    assert result["reused"] is False
    assert result["proposal"]["status"] == "pending"
    assert len(resolver.contexts) == 1
    assert len(repo.proposals) == 1  # la anterior queda como historial fuera del repo fake


async def test_accept_matched_usa_la_via_transaccional() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    result = await ProposeWorkAttribution(repo, _resolver()).execute(310455)  # type: ignore[arg-type]
    proposal_id = result["proposal"]["id"]
    reviewed = await ReviewProposal(repo).execute(proposal_id, "accept", reviewed_by="admin-1", note="ok")  # type: ignore[arg-type]
    assert reviewed == {"id": proposal_id, "status": "accepted"}
    assert len(repo.accepted) == 1
    call = repo.accepted[0]
    assert call["work_id"] == 310455
    assert call["person_id"] == "p1"
    assert call["role_id"] == 1
    assert call["created_by"] == "admin-1"
    assert call["proposal_id"] == proposal_id


async def test_no_se_puede_aceptar_dos_veces() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    result = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    proposal_id = result["proposal"]["id"]
    review = ReviewProposal(repo)
    await review.execute(proposal_id, "accept", reviewed_by="admin-1")  # type: ignore[arg-type]
    with pytest.raises(ProposalStateError):
        await review.execute(proposal_id, "accept", reviewed_by="admin-1")  # type: ignore[arg-type]
    assert len(repo.accepted) == 1


async def test_no_se_puede_aceptar_una_rechazada() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    result = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    proposal_id = result["proposal"]["id"]
    review = ReviewProposal(repo)
    await review.execute(proposal_id, "reject", note="tradicional")  # type: ignore[arg-type]
    with pytest.raises(ProposalStateError):
        await review.execute(proposal_id, "accept")  # type: ignore[arg-type]
    assert repo.accepted == []


async def test_no_se_puede_revisar_una_aceptada() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    result = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    proposal_id = result["proposal"]["id"]
    review = ReviewProposal(repo)
    await review.execute(proposal_id, "accept", reviewed_by="admin-1")  # type: ignore[arg-type]
    with pytest.raises(ProposalStateError):
        await review.execute(proposal_id, "uncertain")  # type: ignore[arg-type]
    assert repo.reviews == []


async def test_accept_sin_persona_resuelta_falla() -> None:
    repo = _FakeRepo()
    result = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    with pytest.raises(ProposalAssignmentError):
        await ReviewProposal(repo).execute(result["proposal"]["id"], "accept")  # type: ignore[arg-type]
    assert repo.accepted == []


async def test_traditional_no_se_puede_aceptar() -> None:
    repo = _FakeRepo()
    result = await ProposeWorkAttribution(
        repo, _resolver(resolution="traditional", person_name=None, role_name=None)
    ).execute(1)  # type: ignore[arg-type]
    with pytest.raises(ProposalAssignmentError):
        await ReviewProposal(repo).execute(result["proposal"]["id"], "accept")  # type: ignore[arg-type]
    assert repo.accepted == []


async def test_reject_escribe_estado_canonico() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    result = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    reviewed = await ReviewProposal(repo).execute(result["proposal"]["id"], "reject", note="tradicional")  # type: ignore[arg-type]
    assert reviewed["status"] == "rejected"
    assert repo.accepted == []


async def test_propuesta_inexistente_falla() -> None:
    repo = _FakeRepo()
    with pytest.raises(LookupError):
        await ReviewProposal(repo).execute(404, "accept")  # type: ignore[arg-type]


async def test_ia_no_configurada_error_claro() -> None:
    repo = _FakeRepo()
    with pytest.raises(AiNotConfiguredError):
        await ProposeWorkAttribution(repo, NullAttributionResolver()).execute(1)  # type: ignore[arg-type]


async def test_fallo_de_gemini_no_guarda_propuesta_falsa() -> None:
    """Si la IA falla (timeout/429/503 agotados), no se persiste ninguna propuesta."""

    class _FailingResolver(FakeAttributionResolver):
        async def propose(self, context: WorkContext) -> AiProposal:
            raise AiUpstreamError("Gemini no disponible tras 3 intentos")

    repo = _FakeRepo()
    with pytest.raises(AiUpstreamError):
        await ProposeWorkAttribution(repo, _FailingResolver()).execute(3)  # type: ignore[arg-type]

    assert repo.proposals == {}
    assert repo.accepted == []
