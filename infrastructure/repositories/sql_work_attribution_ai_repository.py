"""Persistencia de la atribución asistida por IA: propuestas, auditoría y asignación.

Solo lectura/escritura de las tablas nuevas (`work_person_ai_proposals`,
`work_attribution_audit`) y la asignación canónica en `works_person_roles`. Nunca crea
personas ni toca el historial RISM (`work_attribution_history`).

La aceptación es **atómica**: relación + auditoría + cambio de estado en una única
transacción, con comprobación de `rowcount` en cada paso. Si algo falla, rollback: no puede
quedar una propuesta aceptada sin relación, ni una relación sin auditoría.
"""

from __future__ import annotations

import json
from typing import Any

from domain.exceptions import ProposalAssignmentError, ProposalStateError

from infrastructure.db.connection import Database

_MAX_MERGE_HOPS = 10
_MAX_ALIAS_MATCHES = 50
_MAX_GENRES = 5

# Columnas del listado: sin `answer_json` (la respuesta completa del modelo solo se sirve en
# el detalle). `evidence_json` sí viaja porque la tarjeta lo muestra para revisar de un vistazo.
_LIST_COLUMNS = (
    "id, work_id, batch_id, resolution, person_match, candidate_person_id, candidate_name, "
    "role_id, role_name, status, confidence, model, prompt_version, evidence_json, review_note, "
    "reviewed_by, reviewed_at, created_at"
)


def _as_json_list(value: object) -> object:
    """Devuelve la lista JSON ya decodificada (la columna guarda el JSON serializado)."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return value if isinstance(value, list) else []


class SqlWorkAttributionAiRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def work_context(self, work_id: int) -> dict[str, Any] | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT w.id, w.works_title, w.works_song_name, w.works_catalogue, w.works_opus, "
                "w.works_year, w.works_origin, w.works_origin_id, w.works_attr_type, "
                "w.works_attribution_note, w.works_instrumentation "
                "FROM works w WHERE w.id = %s",
                (work_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            await cur.execute(
                "SELECT p.persons_name FROM works_person_roles r "
                "JOIN persons p ON p.persons_id = r.works_person_roles_person_id "
                "WHERE r.works_person_roles_work_id = %s",
                (work_id,),
            )
            result = dict(row)
            result["existing_persons"] = [str(r["persons_name"]) for r in await cur.fetchall()]
            return result

    async def work_genres(self, work_id: int) -> str | None:
        """Géneros de la obra (`work_genres` → `genres`), como lista legible para el prompt."""
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT g.name FROM work_genres wg JOIN genres g ON g.id = wg.genres_id "
                "WHERE wg.works_id = %s ORDER BY g.name LIMIT %s",
                (work_id, _MAX_GENRES),
            )
            names = [str(r["name"]) for r in await cur.fetchall()]
        return ", ".join(names) if names else None

    async def find_person_candidates(self, normalized: str) -> list[dict[str, Any]]:
        """Personas canónicas que coinciden con el nombre normalizado (vía alias).

        Se usa la misma normalización y el mismo espacio de claves que el resto del catálogo
        (`person_aliases_normalized_alias`), siguiendo `persons_merged_into` para no proponer
        identidades fusionadas, y se excluyen las personas ocultas o inactivas.
        """
        if not normalized:
            return []
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT a.person_id AS id FROM persons_aliases a "
                "WHERE a.person_aliases_normalized_alias = %s LIMIT %s",
                (normalized, _MAX_ALIAS_MATCHES),
            )
            matched_ids = [str(r["id"]) for r in await cur.fetchall()]
        canonical = await self._canonical_rows(matched_ids)
        seen: dict[str, dict[str, Any]] = {}
        for row in canonical.values():
            if row.get("persons_merged_into"):
                continue
            if str(row.get("persons_status") or "") != "active":
                continue
            if not int(row.get("persons_visible") or 0):
                continue
            seen[str(row["id"])] = {"id": str(row["id"]), "name": str(row["name"])}
        return sorted(seen.values(), key=lambda item: item["name"])

    async def save_proposal(self, data: dict[str, Any]) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO work_person_ai_proposals "
                "(work_id, batch_id, resolution, person_match, candidate_person_id, candidate_name, "
                " role_id, role_name, status, confidence, model, prompt_version, answer_json, evidence_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s)",
                (
                    data["work_id"], data.get("batch_id"), data["resolution"], data["person_match"],
                    data.get("candidate_person_id"), data.get("candidate_name"), data.get("role_id"),
                    data.get("role_name"), data.get("confidence"), data.get("model"),
                    data.get("prompt_version"), json.dumps(data.get("answer") or {}, ensure_ascii=False),
                    json.dumps(data.get("evidence") or [], ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid or 0)

    async def list_proposals(self, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        where = "WHERE status = %s" if status else ""
        params: list[Any] = [status] if status else []
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"SELECT COUNT(*) AS total FROM work_person_ai_proposals {where}", params)
            total = int((await cur.fetchone())["total"])
            await cur.execute(
                f"SELECT {_LIST_COLUMNS} FROM work_person_ai_proposals {where} "
                f"ORDER BY id DESC LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            return {"items": [dict(r) for r in await cur.fetchall()], "total": total}

    async def get_proposal(self, proposal_id: int) -> dict[str, Any] | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM work_person_ai_proposals WHERE id = %s", (proposal_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def latest_proposal_for_work(self, work_id: int) -> dict[str, Any] | None:
        """Última propuesta de la obra, sea cual sea su estado (para decidir re-propuesta)."""
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM work_person_ai_proposals WHERE work_id = %s ORDER BY id DESC LIMIT 1",
                (work_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def accept_proposal(
        self, *, work_id: int, person_id: str, role_id: int, confidence: float | None,
        proposal_id: int, evidence: object, created_by: str | None, note: str | None,
    ) -> None:
        """Asigna la persona, audita la operación y acepta la propuesta, todo o nada."""
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT IGNORE INTO works_person_roles "
                "(works_person_roles_work_id, works_person_roles_person_id, works_person_roles_role_id) "
                "VALUES (%s,%s,%s)",
                (work_id, person_id, role_id),
            )
            if int(cur.rowcount or 0) != 1:
                raise ProposalAssignmentError(
                    f"works_person_roles no insertada (work={work_id}, person={person_id})"
                )
            await cur.execute(
                "INSERT INTO work_attribution_audit "
                "(work_id, person_id, role_id, operation, source, confidence, proposal_id, "
                " evidence_json, created_by) VALUES (%s,%s,%s,'assign','gemini',%s,%s,%s,%s)",
                (
                    work_id, person_id, role_id, confidence, proposal_id,
                    json.dumps(_as_json_list(evidence), ensure_ascii=False), created_by,
                ),
            )
            await cur.execute(
                "UPDATE work_person_ai_proposals SET status='accepted', reviewed_by=%s, "
                "review_note=%s, reviewed_at=current_timestamp(6) WHERE id=%s AND status='pending'",
                (created_by, note, proposal_id),
            )
            if int(cur.rowcount or 0) != 1:
                raise ProposalStateError()

    async def set_review_if_pending(
        self, proposal_id: int, status: str, reviewed_by: str | None, note: str | None
    ) -> None:
        """Rechaza o marca dudosa una propuesta `pending`; si ya no lo está, no escribe."""
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE work_person_ai_proposals SET status=%s, reviewed_by=%s, review_note=%s, "
                "reviewed_at=current_timestamp(6) WHERE id=%s AND status='pending'",
                (status, reviewed_by, note, proposal_id),
            )
            if int(cur.rowcount or 0) != 1:
                raise ProposalStateError()

    # -- resolución canónica de personas --------------------------------------

    async def _canonical_rows(self, person_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Para cada id de partida, la fila de su persona canónica (siguiendo merged_into)."""
        pending = {pid: pid for pid in dict.fromkeys(person_ids)}
        resolved: dict[str, dict[str, Any]] = {}
        for _ in range(_MAX_MERGE_HOPS):
            if not pending:
                break
            rows = await self._persons_by_ids(list(set(pending.values())))
            following: dict[str, str] = {}
            for original, current in pending.items():
                row = rows.get(current)
                if row is None:
                    continue
                merged_into = row.get("persons_merged_into")
                if merged_into and str(merged_into) != current:
                    following[original] = str(merged_into)
                else:
                    resolved[original] = row
            pending = following
        return resolved

    async def _persons_by_ids(self, person_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not person_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(person_ids))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT persons_id AS id, persons_name AS name, persons_status, persons_visible, "
                f"persons_merged_into FROM persons WHERE persons_id IN ({placeholders})",
                person_ids,
            )
            return {str(r["id"]): dict(r) for r in await cur.fetchall()}
