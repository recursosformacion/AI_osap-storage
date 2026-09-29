"""Consultas administrativas de la relación obra↔persona.

Fuente canónica: `works_person_roles` (work_id, person_id, role_id) + `persons` + `roles`.
Solo lectura; no toca datos ni el modelo.

Endpoints:
  GET /api/admin/work-persons   → listado Obra | Persona | Rol (con ?missing=1: obras sin persona)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from infrastructure.db.connection import Database

from api.dependencies import get_db

router = APIRouter(prefix="/api/admin/work-persons", tags=["admin-works"])

_TITLE = "COALESCE(NULLIF(w.works_title, ''), NULLIF(w.works_song_name, ''), CONCAT('Obra #', w.id))"


def _filters(q: str | None, role: str | None, missing: bool) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if missing:
        where.append("r.works_person_roles_id IS NULL")
    if q and q.strip():
        where.append(f"({_TITLE} LIKE %s OR p.persons_name LIKE %s OR w.works_catalogue LIKE %s)")
        needle = f"%{q.strip()}%"
        params.extend([needle, needle, needle])
    if role and role.strip() and not missing:
        where.append("ro.role_name = %s")
        params.append(role.strip())
    return (" AND ".join(where) if where else "1=1"), params


@router.get("", summary="Relación obra → persona")
async def work_persons(
    q: str | None = Query(default=None),
    role: str | None = Query(default=None, description="Filtra por rol (composer, arranger…)"),
    missing: bool = Query(default=False, description="Solo obras SIN ninguna persona/rol"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    where, params = _filters(q, role, missing)
    base_from = (
        "FROM works w "
        "LEFT JOIN works_person_roles r ON r.works_person_roles_work_id = w.id "
        "LEFT JOIN persons p ON p.persons_id = r.works_person_roles_person_id "
        "LEFT JOIN roles ro ON ro.id = r.works_person_roles_role_id "
    )
    sql = (
        f"SELECT w.id AS work_id, {_TITLE} AS work_title, w.works_catalogue AS catalogue, "
        "r.works_person_roles_person_id AS person_id, p.persons_name AS person_name, "
        "ro.role_name AS role_name "
        f"{base_from} WHERE {where} ORDER BY w.id DESC, ro.id LIMIT %s OFFSET %s"
    )
    count_sql = f"SELECT COUNT(*) AS total {base_from} WHERE {where}"
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(count_sql, params)
        total = int((await cur.fetchone())["total"])
        await cur.execute(sql, [*params, limit, offset])
        items = [dict(row) for row in await cur.fetchall()]
    return {"items": items, "total": total, "missing": missing}
