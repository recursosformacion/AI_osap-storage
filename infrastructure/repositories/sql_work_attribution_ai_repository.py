"""Persistencia de la atribución asistida por IA: propuestas, revisión, auditoría y asignación.

Solo lectura/escritura de las tablas nuevas (`work_person_ai_proposals`, `work_ai_reviews`,
`work_ai_review_relations`, `work_attribution_audit`) y la asignación canónica en
`works_person_roles`. Nunca crea personas ni toca el historial RISM (`work_attribution_history`).

La aceptación es **atómica**: relación + auditoría + cambio de estado en una única
transacción, con comprobación de `rowcount` en cada paso. Si algo falla, rollback: no puede
quedar una propuesta aceptada sin relación, ni una relación sin auditoría.
"""

from __future__ import annotations

import json
from typing import Any

from domain.exceptions import ProposalAssignmentError, ProposalStateError
from domain.services.composer_names import normalize_composer_name

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
                "SELECT p.persons_name AS name, ro.role_name AS role "
                "FROM works_person_roles r "
                "JOIN persons p ON p.persons_id = r.works_person_roles_person_id "
                "JOIN roles ro ON ro.id = r.works_person_roles_role_id "
                "WHERE r.works_person_roles_work_id = %s ORDER BY ro.id",
                (work_id,),
            )
            result = dict(row)
            result["existing_relations"] = [
                {"name": str(r["name"]), "role": str(r["role"])} for r in await cur.fetchall()
            ]
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

    # -- revisión humana: decisión de atribución + personas relacionadas -------

    async def upsert_review(
        self, *, work_id: int, batch_id: str | None, attribution_status: str,
        attribution_note: str | None, attribution_confidence: float | None,
        contradictions: list[str], context: dict[str, Any],
    ) -> int:
        """Crea/refresca la revisión de la obra. Nunca pisa una decisión humana `reviewed`."""
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO work_ai_reviews "
                "(work_id, batch_id, attribution_status, attribution_note, attribution_confidence, "
                " contradictions_json, context_json, status) VALUES (%s,%s,%s,%s,%s,%s,%s,'pending') "
                "ON DUPLICATE KEY UPDATE "
                "  batch_id=VALUES(batch_id), "
                "  contradictions_json=VALUES(contradictions_json), "
                "  context_json=VALUES(context_json), "
                "  attribution_status=IF(status='reviewed', attribution_status, VALUES(attribution_status)), "
                "  attribution_note=IF(status='reviewed', attribution_note, VALUES(attribution_note)), "
                "  attribution_confidence=IF(status='reviewed', attribution_confidence, "
                "    VALUES(attribution_confidence)), "
                "  status=IF(status='reviewed', status, VALUES(status)), "
                "  id=LAST_INSERT_ID(id)",
                (
                    work_id, batch_id, attribution_status, attribution_note, attribution_confidence,
                    json.dumps(contradictions, ensure_ascii=False),
                    json.dumps(context, ensure_ascii=False, default=str),
                ),
            )
            return int(cur.lastrowid or 0)

    async def add_review_relation(
        self, *, review_id: int, work_id: int, person_id: str | None, person_name: str,
        role_id: int, origin: str, confidence: float | None, evidence: object,
    ) -> None:
        """Añade/actualiza una hipótesis de relación; no pisa decisiones humanas."""
        normalized = normalize_composer_name(person_name)
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO work_ai_review_relations "
                "(review_id, work_id, person_id, person_name_raw, person_name_norm, role_id, "
                " decision, origin, confidence, evidence_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  person_id=IF(decision='pending', VALUES(person_id), person_id), "
                "  confidence=IF(decision='pending', VALUES(confidence), confidence), "
                "  evidence_json=IF(decision='pending', VALUES(evidence_json), evidence_json)",
                (
                    review_id, work_id, person_id, person_name[:512], normalized[:191], role_id,
                    origin, confidence, json.dumps(_as_json_list(evidence), ensure_ascii=False),
                ),
            )

    async def ensure_review(self, work_id: int) -> int:
        """Id de la revisión de la obra, creándola si no existe.

        Si la obra ya tiene propuesta IA, la revisión nace con esa atribución (no con
        `unknown`); si no existe propuesta, queda `unknown` a la espera del revisor.
        """
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO work_ai_reviews (work_id, attribution_status, status) "
                "SELECT %s, COALESCE((SELECT p.resolution FROM work_person_ai_proposals p "
                "  WHERE p.work_id = %s ORDER BY p.id DESC LIMIT 1), 'unknown'), 'pending' "
                "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)",
                (work_id, work_id),
            )
            return int(cur.lastrowid or 0)

    async def upsert_human_relation(
        self, *, review_id: int, work_id: int, person_id: str | None, person_name: str,
        role_id: int, decision: str, evidence: object, decided_by: str | None,
    ) -> int:
        """Alta/actualización de una relación decidida por una persona (`origin=human`).

        Idempotente por el índice único `(review_id, role_id, person_name_norm)`. No crea
        personas y no escribe en `works_person_roles`.
        """
        normalized = normalize_composer_name(person_name)
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO work_ai_review_relations "
                "(review_id, work_id, person_id, person_name_raw, person_name_norm, role_id, "
                " decision, origin, confidence, evidence_json, decided_by, decided_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'human',NULL,%s,%s,current_timestamp(6)) "
                "ON DUPLICATE KEY UPDATE "
                "  person_id=VALUES(person_id), person_name_raw=VALUES(person_name_raw), "
                "  decision=VALUES(decision), origin='human', "
                "  evidence_json=IF(VALUES(evidence_json) IN ('[]', 'null'), evidence_json, "
                "    VALUES(evidence_json)), "
                "  decided_by=VALUES(decided_by), "
                "  decided_at=current_timestamp(6), id=LAST_INSERT_ID(id)",
                (
                    review_id, work_id, person_id, person_name[:512], normalized[:191], role_id,
                    decision, json.dumps(_as_json_list(evidence), ensure_ascii=False), decided_by,
                ),
            )
            return int(cur.lastrowid or 0)

    async def person_exists(self, person_id: str) -> bool:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1 AS ok FROM persons WHERE persons_id = %s LIMIT 1", (person_id,))
            return (await cur.fetchone()) is not None

    async def person_name(self, person_id: str) -> str | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT persons_name FROM persons WHERE persons_id = %s", (person_id,))
            row = await cur.fetchone()
            return str(row["persons_name"]) if row else None

    async def work_exists(self, work_id: int) -> bool:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1 AS ok FROM works WHERE id = %s LIMIT 1", (work_id,))
            return (await cur.fetchone()) is not None

    async def get_review(self, work_id: int) -> dict[str, Any] | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM work_ai_reviews WHERE work_id = %s", (work_id,))
            row = await cur.fetchone()
            if row is None:
                return None
            review = dict(row)
            await cur.execute(
                "SELECT id, person_id, person_name_raw, role_id, decision, origin, confidence, "
                "evidence_json, decided_by, decided_at FROM work_ai_review_relations "
                "WHERE review_id = %s ORDER BY role_id, id",
                (review["id"],),
            )
            review["relations"] = [dict(r) for r in await cur.fetchall()]
            return review

    async def list_reviews(self, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        where = "WHERE status = %s" if status else ""
        params: list[Any] = [status] if status else []
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"SELECT COUNT(*) AS total FROM work_ai_reviews {where}", params)
            total = int((await cur.fetchone())["total"])
            await cur.execute(
                f"SELECT id, work_id, batch_id, attribution_status, status, reviewed_by, reviewed_at, "
                f"created_at FROM work_ai_reviews {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            return {"items": [dict(r) for r in await cur.fetchall()], "total": total}

    async def set_review_attribution(
        self, work_id: int, attribution_status: str, note: str | None, reviewed_by: str | None
    ) -> bool:
        """Decisión humana sobre la atribución de la obra; marca la revisión como `reviewed`."""
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE work_ai_reviews SET attribution_status=%s, attribution_note=%s, status='reviewed', "
                "reviewed_by=%s, reviewed_at=current_timestamp(6) WHERE work_id=%s",
                (attribution_status, note, reviewed_by, work_id),
            )
            return int(cur.rowcount or 0) == 1

    async def set_relation_decision(
        self, relation_id: int, decision: str, reviewed_by: str | None = None
    ) -> dict[str, Any] | None:
        """Decisión humana sobre una relación (persona × rol)."""
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE work_ai_review_relations SET decision=%s, decided_by=%s, "
                "decided_at=current_timestamp(6) WHERE id=%s",
                (decision, reviewed_by, relation_id),
            )
            if int(cur.rowcount or 0) != 1:
                return None
            await cur.execute(
                "SELECT review_id, work_id FROM work_ai_review_relations WHERE id=%s", (relation_id,)
            )
            return dict(await cur.fetchone())

    async def mark_review_reviewed(self, work_id: int, reviewed_by: str | None) -> None:
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE work_ai_reviews SET status='reviewed', reviewed_by=%s, "
                "reviewed_at=current_timestamp(6) WHERE work_id=%s",
                (reviewed_by, work_id),
            )

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
