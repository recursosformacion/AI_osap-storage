"""Casos de uso de la atribución asistida por IA (MVP: propuesta y revisión humana)."""

from __future__ import annotations

import re
from typing import Any

from domain.ports.work_attribution_ai import PROMPT_VERSION, IWorkAttributionResolver, WorkContext
from infrastructure.ai.errors import AiNotConfiguredError
from infrastructure.repositories.sql_work_attribution_ai_repository import (
    SqlWorkAttributionAiRepository,
)

_DEFAULT_ROLE = "Compositor/a"


def _normalize(name: str) -> str:
    text = re.sub(r"[^0-9a-záéíóúüñ ]+", " ", name.lower())
    return re.sub(r"\s+", " ", text).strip()


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

        candidate_person_id = None
        candidate_name = proposal.person_name
        if proposal.resolution != "identified" or not candidate_name:
            person_match = "not_applicable"
            candidate_name = None
        else:
            candidates = await self._repo.find_person_candidates(candidate_name, _normalize(candidate_name))
            if len(candidates) == 1:
                person_match = "matched"
                candidate_person_id = str(candidates[0]["id"])
                candidate_name = str(candidates[0]["name"])
            elif len(candidates) > 1:
                person_match = "ambiguous"
            else:
                person_match = "unresolved"

        role_name = proposal.role_name
        role_id = await self._repo.role_id_by_name(role_name) if role_name else None
        if proposal.resolution == "identified" and role_id is None:
            role_name = _DEFAULT_ROLE
            role_id = await self._repo.role_id_by_name(role_name)

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
    """Acepta/rechaza/marca dudosa una propuesta. Al aceptar, asigna por la vía canónica."""

    def __init__(self, repo: SqlWorkAttributionAiRepository) -> None:
        self._repo = repo

    async def execute(
        self, proposal_id: int, action: str, reviewed_by: str | None = None, note: str | None = None
    ) -> dict[str, Any]:
        proposal = await self._repo.get_proposal(proposal_id)
        if proposal is None:
            raise LookupError(f"propuesta no encontrada: {proposal_id}")
        if action == "accept":
            person_id = proposal.get("candidate_person_id")
            role_id = proposal.get("role_id")
            if not person_id or not role_id:
                raise AiNotConfiguredError(
                    "no se puede aceptar: requiere persona identificada (matched) y rol"
                )
            await self._repo.assign_person_role(int(proposal["work_id"]), str(person_id), int(role_id))
            await self._repo.add_history(
                work_id=int(proposal["work_id"]), person_id=str(person_id), role_id=int(role_id),
                operation="assign", source="gemini", confidence=proposal.get("confidence"),
                proposal_id=proposal_id, evidence=proposal.get("evidence_json"), created_by=reviewed_by,
            )
            status = "accepted"
        elif action == "reject":
            status = "rejected"
        elif action == "uncertain":
            status = "uncertain"
        else:
            raise ValueError("acción inválida (accept|reject|uncertain)")
        await self._repo.set_review(proposal_id, status, reviewed_by, note)
        return {"id": proposal_id, "status": status}


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
