"""Casos de uso de la atribución asistida por IA (MVP: propuesta y revisión humana).

Reglas del MVP:
- La IA solo propone; nunca asigna ni crea personas.
- La revisión solo actúa sobre propuestas `pending` (pending → accepted|rejected|uncertain).
- Aceptar exige persona resuelta (`matched`) y usa el rol canónico de compositor: el modelo
  no decide el rol.
- La aceptación es atómica en el repositorio (relación + auditoría + estado).
"""

from __future__ import annotations

from typing import Any

from domain.exceptions import ProposalAssignmentError, ProposalStateError
from domain.ports.work_attribution_ai import PROMPT_VERSION, IWorkAttributionResolver, WorkContext
from domain.services.composer_names import normalize_composer_name
from infrastructure.repositories.sql_work_attribution_ai_repository import (
    SqlWorkAttributionAiRepository,
)
from infrastructure.repositories.sql_work_repository import ROLE_COMPOSER

# El rol lo fija el dominio (no el modelo). `ROLE_COMPOSER` es la constante que usan las demás
# vías de asignación; el nombre es el vocabulario de `roles.role_name`.
_COMPOSER_ROLE_NAME = "composer"


class ProposeWorkAttribution:
    """Consulta la IA para una obra y guarda una propuesta. Nunca asigna."""

    def __init__(self, repo: SqlWorkAttributionAiRepository, resolver: IWorkAttributionResolver) -> None:
        self._repo = repo
        self._resolver = resolver

    async def execute(self, work_id: int, batch_id: str | None = None) -> dict[str, Any]:
        existing = await self._repo.existing_proposal_for_work(work_id)
        if existing is not None:
            return existing
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
            instrumentation=row.get("works_instrumentation"),
            attr_type=row.get("works_attr_type"),
            attribution_note=row.get("works_attribution_note"),
            existing_persons=list(row.get("existing_persons") or []),
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
        saved = await self._repo.get_proposal(proposal_id)
        return saved or {"id": proposal_id}


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
