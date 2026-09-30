"""Casos de uso de la atribución asistida por IA (MVP: propuesta y revisión humana).

Reglas del MVP:
- La IA solo propone; nunca asigna ni crea personas.
- La revisión solo actúa sobre propuestas `pending` (pending → accepted|rejected|uncertain).
- Aceptar exige persona resuelta (`matched`) y usa el rol canónico de compositor: el modelo
  no decide el rol.
- La aceptación es atómica en el repositorio (relación + auditoría + estado).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from domain.exceptions import ProposalAssignmentError, ProposalStateError
from domain.ports.work_attribution_ai import (
    PROMPT_VERSION,
    AiProposal,
    IWorkAttributionResolver,
    WorkContext,
)
from domain.services.composer_names import normalize_composer_name
from domain.services.person_roles import ROLE_IDS
from infrastructure.repositories.sql_work_attribution_ai_repository import (
    SqlWorkAttributionAiRepository,
)
from infrastructure.repositories.sql_work_repository import ROLE_COMPOSER

# El rol lo fija el dominio (no el modelo). `ROLE_COMPOSER` es la constante que usan las demás
# vías de asignación; el nombre es el vocabulario de `roles.role_name`.
_COMPOSER_ROLE_NAME = "composer"


class ProposeWorkAttribution:
    """Consulta la IA para una obra y guarda una propuesta. Nunca asigna.

    Semántica de re-propuesta (explícita, sin llamadas accidentales a Gemini):
    - Si la obra ya tiene propuesta (`pending`, `accepted`, `uncertain` o `rejected`), se
      devuelve esa misma con `reused=True` y **no** se consulta a la IA.
    - Con `force=True` se consulta de nuevo y se guarda una propuesta nueva; las anteriores
      quedan como historial (el revisor ve siempre la última, orden por id).
    - `pending` bloquea la revisión nueva; `accepted` bloquea la aceptación repetida.
    """

    def __init__(self, repo: SqlWorkAttributionAiRepository, resolver: IWorkAttributionResolver) -> None:
        self._repo = repo
        self._resolver = resolver

    async def execute(
        self, work_id: int, batch_id: str | None = None, force: bool = False
    ) -> dict[str, Any]:
        latest = await self._repo.latest_proposal_for_work(work_id)
        if latest is not None and not force:
            return {"proposal": latest, "reused": True}
        row = await self._repo.work_context(work_id)
        if row is None:
            raise LookupError(f"obra no encontrada: {work_id}")
        context = WorkContext(
            work_id=work_id,
            title=row.get("works_title") or row.get("works_song_name"),
            source=row.get("works_origin"),
            source_id=row.get("works_origin_id"),
            catalogue=row.get("works_catalogue"),
            year=row.get("works_year"),
            opus=row.get("works_opus"),
            genre=await self._repo.work_genres(work_id),
            instrumentation=row.get("works_instrumentation"),
            attr_type=row.get("works_attr_type"),
            attribution_note=row.get("works_attribution_note"),
            existing_relations=list(row.get("existing_relations") or []),
        )
        proposal = await self._resolver.propose(context)

        candidate_person_id: str | None = None
        candidate_name: str | None = None
        person_match = "not_applicable"
        role_id: int | None = None
        role_name: str | None = None
        if proposal.resolution == "identified" and proposal.person_name:
            candidate_name = proposal.person_name
            candidates = await self._repo.find_person_candidates(
                normalize_composer_name(proposal.person_name)
            )
            if len(candidates) == 1:
                person_match = "matched"
                candidate_person_id = str(candidates[0]["id"])
                candidate_name = str(candidates[0]["name"])
            elif len(candidates) > 1:
                person_match = "ambiguous"
            else:
                person_match = "unresolved"
            # Rol canónico de compositor (el modelo no decide el rol ni quién es la persona).
            role_id = ROLE_COMPOSER
            role_name = _COMPOSER_ROLE_NAME

        proposal_id = await self._repo.save_proposal(
            {
                "work_id": work_id,
                "batch_id": batch_id,
                "resolution": proposal.resolution,
                "person_match": person_match,
                "candidate_person_id": candidate_person_id,
                "candidate_name": candidate_name,
                "role_id": role_id,
                "role_name": role_name,
                "confidence": proposal.confidence,
                "model": getattr(self._resolver, "model", None),
                "prompt_version": PROMPT_VERSION,
                "answer": proposal.raw,
                "evidence": proposal.evidence,
            }
        )
        await self._persist_review(work_id, batch_id, row, context, proposal, candidate_person_id,
                                   candidate_name, person_match)
        saved = await self._repo.get_proposal(proposal_id)
        return {"proposal": saved or {"id": proposal_id}, "reused": False}

    async def _persist_review(
        self, work_id: int, batch_id: str | None, row: dict[str, Any], context: WorkContext,
        proposal: AiProposal, candidate_person_id: str | None, candidate_name: str | None,
        person_match: str,
    ) -> None:
        """Guarda el artefacto de revisión: atribución de la obra + personas relacionadas.

        Nada de esto escribe en `works_person_roles`: son hipótesis con `decision=pending`.
        """
        relations: list[dict[str, Any]] = []
        if proposal.resolution == "identified" and proposal.person_name:
            evidence = list(proposal.evidence)
            if person_match != "matched":
                evidence.append({"type": "person_match", "text": person_match})
            relations.append(
                {
                    "person_id": candidate_person_id,
                    "person_name": candidate_name or proposal.person_name,
                    "role_key": "composer",
                    "confidence": proposal.confidence,
                    "evidence": evidence,
                }
            )
        for relation in proposal.relations:
            if relation.role_key == "composer":
                continue  # la vía canónica del compositor ya está cubierta arriba
            matches = await self._repo.find_person_candidates(
                normalize_composer_name(relation.person_name)
            )
            relations.append(
                {
                    "person_id": str(matches[0]["id"]) if len(matches) == 1 else None,
                    "person_name": relation.person_name,
                    "role_key": relation.role_key,
                    "confidence": relation.confidence,
                    "evidence": relation.evidence,
                }
            )

        review_id = await self._repo.upsert_review(
            work_id=work_id,
            batch_id=batch_id,
            attribution_status=proposal.resolution,
            attribution_note=row.get("works_attribution_note"),
            attribution_confidence=proposal.confidence,
            contradictions=list(proposal.contradictions),
            context=asdict(context),
        )
        for item in relations:
            await self._repo.add_review_relation(
                review_id=review_id,
                work_id=work_id,
                person_id=item["person_id"],
                person_name=str(item["person_name"]),
                role_id=ROLE_IDS[str(item["role_key"])],
                origin="gemini",
                confidence=item["confidence"],
                evidence=item["evidence"],
            )


class ReviewProposal:
    """Acepta/rechaza/marca dudosa una propuesta `pending`.

    Al aceptar, la asignación, su auditoría y el cambio de estado ocurren en una única
    transacción del repositorio. El `reviewed_by` es la identidad autenticada del revisor.
    """

    def __init__(self, repo: SqlWorkAttributionAiRepository) -> None:
        self._repo = repo

    async def execute(
        self, proposal_id: int, action: str, reviewed_by: str | None = None, note: str | None = None
    ) -> dict[str, Any]:
        proposal = await self._repo.get_proposal(proposal_id)
        if proposal is None:
            raise LookupError(f"propuesta no encontrada: {proposal_id}")
        status = str(proposal.get("status") or "")
        if status != "pending":
            raise ProposalStateError(status)
        if action == "accept":
            person_id = proposal.get("candidate_person_id")
            role_id = proposal.get("role_id")
            if not person_id or not role_id:
                raise ProposalAssignmentError(
                    "no se puede aceptar: requiere persona identificada (matched) y rol"
                )
            await self._repo.accept_proposal(
                work_id=int(proposal["work_id"]),
                person_id=str(person_id),
                role_id=int(role_id),
                confidence=proposal.get("confidence"),
                proposal_id=proposal_id,
                evidence=proposal.get("evidence_json"),
                created_by=reviewed_by,
                note=note,
            )
            return {"id": proposal_id, "status": "accepted"}
        if action in ("reject", "uncertain"):
            new_status = "rejected" if action == "reject" else "uncertain"
            await self._repo.set_review_if_pending(proposal_id, new_status, reviewed_by, note)
            return {"id": proposal_id, "status": new_status}
        raise ValueError("acción inválida (accept|reject|uncertain)")


class ListWorkAttributionProposals:
    def __init__(self, repo: SqlWorkAttributionAiRepository) -> None:
        self._repo = repo

    async def execute(self, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        return await self._repo.list_proposals(status, limit, offset)


class GetWorkAttributionProposal:
    def __init__(self, repo: SqlWorkAttributionAiRepository) -> None:
        self._repo = repo

    async def execute(self, proposal_id: int) -> dict[str, Any]:
        proposal = await self._repo.get_proposal(proposal_id)
        if proposal is None:
            raise LookupError(f"propuesta no encontrada: {proposal_id}")
        return proposal


class GetWorkReview:
    """Revisión de una obra: atribución + personas relacionadas (artefacto de decisiones)."""

    def __init__(self, repo: SqlWorkAttributionAiRepository) -> None:
        self._repo = repo

    async def execute(self, work_id: int) -> dict[str, Any]:
        review = await self._repo.get_review(work_id)
        if review is None:
            raise LookupError(f"revisión no encontrada: {work_id}")
        return review


class ListWorkReviews:
    def __init__(self, repo: SqlWorkAttributionAiRepository) -> None:
        self._repo = repo

    async def execute(self, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        return await self._repo.list_reviews(status, limit, offset)


class SetWorkAttribution:
    """Decisión humana sobre la atribución de la obra (identified/anonymous/traditional/unknown)."""

    def __init__(self, repo: SqlWorkAttributionAiRepository) -> None:
        self._repo = repo

    async def execute(
        self, work_id: int, attribution_status: str, note: str | None, reviewed_by: str | None
    ) -> dict[str, Any]:
        if attribution_status not in ("identified", "anonymous", "traditional", "unknown"):
            raise ValueError("attribution_status inválido")
        updated = await self._repo.set_review_attribution(work_id, attribution_status, note, reviewed_by)
        if not updated:
            raise LookupError(f"revisión no encontrada: {work_id}")
        return {"work_id": work_id, "attribution_status": attribution_status, "status": "reviewed"}


class ReviewRelation:
    """Decisión humana sobre una relación (persona × rol)."""

    def __init__(self, repo: SqlWorkAttributionAiRepository) -> None:
        self._repo = repo

    async def execute(self, relation_id: int, decision: str, reviewed_by: str | None) -> dict[str, Any]:
        if decision not in ("pending", "accepted", "rejected", "uncertain"):
            raise ValueError("decision inválida")
        row = await self._repo.set_relation_decision(relation_id, decision)
        if row is None:
            raise LookupError(f"relación no encontrada: {relation_id}")
        await self._repo.mark_review_reviewed(int(row["work_id"]), reviewed_by)
        return {"id": relation_id, "work_id": row["work_id"], "decision": decision}
