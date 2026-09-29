"""Persistencia de la atribución asistida por IA: propuestas, historial y asignación.

Solo lectura/escritura de las tablas nuevas (`work_person_ai_proposals`,
`work_attribution_history`) y la asignación canónica en `works_person_roles`.
Nunca crea personas.
"""

from __future__ import annotations

import json
from typing import Any

from infrastructure.db.connection import Database


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
            row = dict(row)
            row["existing_persons"] = [str(r["persons_name"]) for r in await cur.fetchall()]
            return row

    async def find_person_candidates(self, name: str, normalized: str) -> list[dict[str, Any]]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT p.persons_id AS id, p.persons_name AS name "
                "FROM persons p LEFT JOIN persons_aliases a ON a.person_id = p.persons_id "
                "WHERE p.persons_name = %s OR a.person_aliases_normalized_alias = %s "
                "ORDER BY p.persons_name LIMIT 20",
                (name, normalized),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def role_id_by_name(self, role_name: str) -> int | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT id FROM roles WHERE role_name = %s LIMIT 1", (role_name,))
            row = await cur.fetchone()
            return int(row["id"]) if row else None

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
                f"SELECT * FROM work_person_ai_proposals {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            return {"items": [dict(r) for r in await cur.fetchall()], "total": total}

    async def get_proposal(self, proposal_id: int) -> dict[str, Any] | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM work_person_ai_proposals WHERE id = %s", (proposal_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def existing_proposal_for_work(self, work_id: int) -> dict[str, Any] | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM work_person_ai_proposals WHERE work_id = %s AND status <> 'rejected' "
                "ORDER BY id DESC LIMIT 1",
                (work_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def assign_person_role(self, work_id: int, person_id: str, role_id: int) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT IGNORE INTO works_person_roles "
                "(works_person_roles_work_id, works_person_roles_person_id, works_person_roles_role_id) "
                "VALUES (%s,%s,%s)",
                (work_id, person_id, role_id),
            )

    async def add_history(
        self, *, work_id: int, person_id: str, role_id: int, operation: str, source: str,
        confidence: float | None, proposal_id: int | None, evidence: object, created_by: str | None,
    ) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO work_attribution_history "
                "(work_id, person_id, role_id, operation, source, confidence, proposal_id, "
                " evidence_json, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    work_id, person_id, role_id, operation, source, confidence, proposal_id,
                    json.dumps(evidence or [], ensure_ascii=False), created_by,
                ),
            )

    async def set_review(self, proposal_id: int, status: str, reviewed_by: str | None, note: str | None) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE work_person_ai_proposals SET status=%s, reviewed_by=%s, review_note=%s, "
                "reviewed_at=current_timestamp(6) WHERE id=%s",
                (status, reviewed_by, note, proposal_id),
            )
