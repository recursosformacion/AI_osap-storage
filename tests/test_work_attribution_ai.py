"""Tests del MVP de atribución asistida por IA (propuesta, re-propuesta y revisión humana)."""

from __future__ import annotations

from typing import Any

import pytest
from application.use_cases.work_attribution_ai import (
    GetWorkReview,
    ProposeWorkAttribution,
    ReviewProposal,
    ReviewRelation,
    SetWorkAttribution,
)
from domain.exceptions import ProposalAssignmentError, ProposalStateError
from domain.ports.work_attribution_ai import AiProposal, AiRelation, WorkContext
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
        self.candidates_by_name: dict[str, list[dict]] = {}
        self.accepted: list[dict] = []
        self.reviews: list[tuple[int, str, str | None, str | None]] = []
        self.normalized_searched: list[str] = []
        self.latest: dict | None = None
        self.genre: str | None = None
        self.existing_relations: list[dict] = []
        self.review_rows: dict[int, dict] = {}
        self.review_relations: list[dict] = []
        self.review_reviewed: list[tuple[int, str | None]] = []
        self._seq = 0
        self._review_seq = 0

    async def latest_proposal_for_work(self, work_id: int) -> dict | None:
        return self.latest

    async def work_context(self, work_id: int) -> dict:
        return {
            "id": work_id,
            "works_title": "Obra X",
            "works_attribution_note": None,
            "existing_relations": self.existing_relations,
        }

    async def work_genres(self, work_id: int) -> str | None:
        return self.genre

    async def find_person_candidates(self, normalized: str) -> list[dict]:
        self.normalized_searched.append(normalized)
        if normalized in self.candidates_by_name:
            return self.candidates_by_name[normalized]
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

    # -- revisión humana ----------------------------------------------------

    async def upsert_review(self, **kwargs: object) -> int:
        work_id = int(kwargs["work_id"])  # type: ignore[arg-type]
        row = self.review_rows.setdefault(
            work_id,
            {"id": len(self.review_rows) + 1, "work_id": work_id, "status": "pending", "relations": []},
        )
        row.update(
            {
                "attribution_status": kwargs.get("attribution_status"),
                "attribution_note": kwargs.get("attribution_note"),
                "contradictions": kwargs.get("contradictions"),
                "context": kwargs.get("context"),
                "upserts": int(row.get("upserts", 0)) + 1,
            }
        )
        return int(row["id"])

    async def add_review_relation(self, **kwargs: object) -> None:
        row = dict(kwargs)
        row.setdefault("decision", "pending")
        self.review_relations.append(row)

    async def get_review(self, work_id: int) -> dict | None:
        return self.review_rows.get(work_id)

    async def list_reviews(self, status: str | None, limit: int, offset: int) -> dict:
        items = list(self.review_rows.values())
        return {"items": items, "total": len(items)}

    async def set_review_attribution(
        self, work_id: int, attribution_status: str, note: str | None, reviewed_by: str | None
    ) -> bool:
        row = self.review_rows.get(work_id)
        if row is None:
            return False
        row.update({"attribution_status": attribution_status, "status": "reviewed"})
        return True

    async def set_relation_decision(self, relation_id: int, decision: str) -> dict | None:
        for relation in self.review_relations:
            if int(relation.get("_id", -1)) == relation_id:
                relation["decision"] = decision
                return {"review_id": 1, "work_id": relation["work_id"]}
        return None

    async def mark_review_reviewed(self, work_id: int, reviewed_by: str | None) -> None:
        self.review_reviewed.append((work_id, reviewed_by))
        if work_id in self.review_rows:
            self.review_rows[work_id]["status"] = "reviewed"


def _resolver(**kwargs: object) -> _CapturingResolver:
    return _CapturingResolver(
        proposal=AiProposal(
            resolution=kwargs.get("resolution", "identified"),  # type: ignore[arg-type]
            person_name=kwargs.get("person_name", "Louise Farrenc"),  # type: ignore[arg-type]
            role_name=kwargs.get("role_name", "Arreglista"),  # type: ignore[arg-type]
            confidence=kwargs.get("confidence", 0.96),  # type: ignore[arg-type]
            evidence=[{"type": "source_metadata", "text": "PDMX"}],
            relations=kwargs.get("relations", []),  # type: ignore[arg-type]
            contradictions=kwargs.get("contradictions", []),  # type: ignore[arg-type]
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


# --- revisión humana: atribución + personas relacionadas ----------------------


async def test_propose_crea_revision_con_relacion_de_compositor() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]

    await ProposeWorkAttribution(repo, _resolver()).execute(310455)  # type: ignore[arg-type]

    review = repo.review_rows[310455]
    assert review["attribution_status"] == "identified"
    assert review["context"]["work_id"] == 310455
    assert [
        (r["person_id"], r["role_id"], r["decision"], r["origin"]) for r in repo.review_relations
    ] == [("p1", 1, "pending", "gemini")]
    assert repo.accepted == []  # nada escribió en works_person_roles


async def test_propose_anonymous_no_crea_relaciones() -> None:
    repo = _FakeRepo()

    await ProposeWorkAttribution(
        repo, _resolver(resolution="anonymous", person_name=None, role_name=None)
    ).execute(1)  # type: ignore[arg-type]

    assert repo.review_rows[1]["attribution_status"] == "anonymous"
    assert repo.review_relations == []


async def test_propose_guarda_personas_relacionadas_con_su_rol() -> None:
    repo = _FakeRepo()
    repo.candidates_by_name = {
        "louise farrenc": [{"id": "p1", "name": "Louise Farrenc"}],
        "jan novak": [{"id": "p9", "name": "Jan Novák"}],
        "desconocidisimo": [],
    }
    relaciones = [
        AiRelation(person_name="Jan Novák", role_key="arranger", confidence=0.5,
                   evidence=[{"type": "editorial", "text": "arreglo"}]),
        AiRelation(person_name="Desconocidísimo", role_key="librettist", confidence=0.3),
    ]

    await ProposeWorkAttribution(repo, _resolver(relations=relaciones)).execute(1)  # type: ignore[arg-type]

    stored = [
        (r["person_id"], r["role_id"], r["person_name"], r["decision"]) for r in repo.review_relations
    ]
    assert stored == [
        ("p1", 1, "Louise Farrenc", "pending"),      # compositor (vía canónica)
        ("p9", 3, "Jan Novák", "pending"),           # arreglista resuelto
        (None, 2, "Desconocidísimo", "pending"),     # letrista sin coincidencia
    ]
    assert repo.accepted == []


async def test_contradicciones_se_guardan_en_la_revision() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]

    await ProposeWorkAttribution(
        repo, _resolver(contradictions=["El título no concuerda con el catálogo"])
    ).execute(1)  # type: ignore[arg-type]

    assert repo.review_rows[1]["contradictions"] == ["El título no concuerda con el catálogo"]


async def test_reused_no_toca_la_revision() -> None:
    repo = _FakeRepo()
    repo.latest = {"id": 9, "work_id": 1, "status": "pending"}

    result = await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]

    assert result["reused"] is True
    assert repo.review_rows == {}
    assert repo.review_relations == []


async def test_decision_de_relacion_marca_la_revision_como_revisada() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]
    repo.review_relations[0]["_id"] = 5

    result = await ReviewRelation(repo).execute(5, "accepted", reviewed_by="admin-1")  # type: ignore[arg-type]

    assert result == {"id": 5, "work_id": 1, "decision": "accepted"}
    assert repo.review_relations[0]["decision"] == "accepted"
    assert repo.review_reviewed == [(1, "admin-1")]
    assert repo.accepted == []  # la decisión no aplica nada


async def test_decision_de_atribucion_marca_la_revision() -> None:
    repo = _FakeRepo()
    repo.candidates = [{"id": "p1", "name": "Louise Farrenc"}]
    await ProposeWorkAttribution(repo, _resolver()).execute(1)  # type: ignore[arg-type]

    result = await SetWorkAttribution(repo).execute(1, "traditional", "popular checa", "admin-1")  # type: ignore[arg-type]

    assert result["attribution_status"] == "traditional"
    assert repo.review_rows[1]["status"] == "reviewed"
    assert repo.review_rows[1]["attribution_status"] == "traditional"


async def test_revision_inexistente_falla() -> None:
    repo = _FakeRepo()
    with pytest.raises(LookupError):
        await GetWorkReview(repo).execute(404)  # type: ignore[arg-type]
    with pytest.raises(LookupError):
        await SetWorkAttribution(repo).execute(404, "unknown", None, None)  # type: ignore[arg-type]
    with pytest.raises(LookupError):
        await ReviewRelation(repo).execute(99, "accepted", None)  # type: ignore[arg-type]


async def test_decision_invalida_falla() -> None:
    repo = _FakeRepo()
    with pytest.raises(ValueError):
        await SetWorkAttribution(repo).execute(1, "inventada", None, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await ReviewRelation(repo).execute(1, "inventada", None)  # type: ignore[arg-type]
