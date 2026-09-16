"""Gestión de relaciones de una obra desde el mantenimiento.

Permite al formulario de `works` montar y desmontar los enlaces con:
`works_person_roles` (persona + rol), `work_ensembles`, `work_genres`,
`work_instruments`, `work_language` y `work_voices`.

Endpoints:
  GET    /api/admin/works/options/{relation}      → opciones para el desplegable
  GET    /api/admin/works/{work_id}/relations     → relaciones actuales (con etiquetas)
  POST   /api/admin/works/{work_id}/relations/{relation}   body {id[, role_id]}  → añade
  DELETE /api/admin/works/{work_id}/relations/{relation}   body {id[, role_id]}  → quita
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from infrastructure.db.connection import Database

from api.dependencies import get_db

router = APIRouter(prefix="/api/admin/works", tags=["admin-works"])

# relation -> (tabla, columna de la obra, columnas de la relación, JOIN de etiqueta)
RELATIONS: dict[str, dict[str, Any]] = {
    "person_roles": {
        "table": "works_person_roles",
        "work_col": "works_person_roles_work_id",
        "cols": ["works_person_roles_person_id", "works_person_roles_role_id"],
        "primary": "works_person_roles_person_id",
        "roles_col": "works_person_roles_role_id",
        "label_sql": (
            "SELECT r.works_person_roles_id AS id, "
            "r.works_person_roles_person_id AS ref_id, r.works_person_roles_role_id AS role_id, "
            "p.persons_name AS label, ro.role_name AS role_name "
            "FROM works_person_roles r "
            "LEFT JOIN persons p ON p.persons_id = r.works_person_roles_person_id "
            "LEFT JOIN roles ro ON ro.id = r.works_person_roles_role_id "
            "WHERE r.works_person_roles_work_id = %s "
            "ORDER BY ro.id, p.persons_name"
        ),
    },
    "genres": {
        "table": "work_genres",
        "work_col": "works_id",
        "cols": ["genres_id"],
        "primary": "genres_id",
        "label_sql": (
            "SELECT g.id AS ref_id, g.name AS label FROM work_genres wg "
            "JOIN genres g ON g.id = wg.genres_id WHERE wg.works_id = %s ORDER BY g.name"
        ),
    },
    "instruments": {
        "table": "work_instruments",
        "work_col": "works_id",
        "cols": ["instruments_id"],
        "primary": "instruments_id",
        "label_sql": (
            "SELECT i.id AS ref_id, COALESCE(i.name_es, i.name_en) AS label, "
            "wi.work_instruments_quantity AS quantity FROM work_instruments wi "
            "JOIN instruments i ON i.id = wi.instruments_id "
            "WHERE wi.works_id = %s ORDER BY i.name_es"
        ),
    },
    "languages": {
        "table": "work_language",
        "work_col": "works_id",
        "cols": ["languages_id"],
        "primary": "languages_id",
        "label_sql": (
            "SELECT l.id AS ref_id, COALESCE(l.languages_name, l.languages_code) AS label "
            "FROM work_language wl JOIN languages l ON l.id = wl.languages_id "
            "WHERE wl.works_id = %s ORDER BY label"
        ),
    },
    "voices": {
        "table": "work_voices",
        "work_col": "works_id",
        "cols": ["voices_id"],
        "primary": "voices_id",
        "label_sql": (
            "SELECT v.id AS ref_id, v.voices_name AS label, wv.work_voices_context AS context "
            "FROM work_voices wv JOIN voices v ON v.id = wv.voices_id "
            "WHERE wv.works_id = %s ORDER BY v.voices_sort, v.voices_name"
        ),
    },
    "ensembles": {
        "table": "work_ensembles",
        "work_col": "works_id",
        "cols": ["ensembles_id"],
        "primary": "ensembles_id",
        "label_sql": (
            "SELECT e.id AS ref_id, COALESCE(e.ensembles_name, e.ensembles_code) AS label "
            "FROM work_ensembles we JOIN ensembles e ON e.id = we.ensembles_id "
            "WHERE we.works_id = %s ORDER BY e.ensembles_code"
        ),
    },
}

OPTIONS_SQL: dict[str, str] = {
    "person_roles": (
        "SELECT p.persons_id AS value, p.persons_name AS label, "
        "ro.id AS role_id, ro.role_name AS role_name "
        "FROM persons p CROSS JOIN roles ro "
        "WHERE p.persons_visible = 1 ORDER BY p.persons_name, ro.id"
    ),
    "genres": "SELECT id AS value, name AS label FROM genres ORDER BY name",
    "instruments": (
        "SELECT id AS value, COALESCE(name_es, name_en) AS label FROM instruments ORDER BY label"
    ),
    "languages": (
        "SELECT id AS value, COALESCE(languages_name, languages_code) AS label "
        "FROM languages ORDER BY label"
    ),
    "voices": "SELECT id AS value, voices_name AS label FROM voices ORDER BY voices_sort",
    "ensembles": (
        "SELECT id AS value, COALESCE(ensembles_name, ensembles_code) AS label "
        "FROM ensembles ORDER BY ensembles_code"
    ),
}

OPTIONS_LIMIT = {"person_roles": 500}


def _relation(name: str) -> dict[str, Any]:
    if name not in RELATIONS:
        raise HTTPException(status_code=404, detail=f"relación desconocida: {name}")
    return RELATIONS[name]


@router.get("/options/{relation}", summary="Opciones del desplegable de una relación")
async def relation_options(relation: str, q: str | None = None, db: Database = Depends(get_db)):
    _relation(relation)  # valida el nombre
    sql = OPTIONS_SQL[relation]
    params: list[Any] = []
    if q and q.strip():
        if relation == "person_roles":
            sql = sql.replace("WHERE p.persons_visible = 1", "WHERE p.persons_visible = 1 AND p.persons_name LIKE %s")
            params.append(f"%{q.strip()}%")
        else:
            sql = sql.replace("ORDER BY", "WHERE label LIKE %s ORDER BY")
            params.append(f"%{q.strip()}%")
    limit = OPTIONS_LIMIT.get(relation)
    if limit:
        sql += f" LIMIT {limit}"
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
        return {"relation": relation, "options": [dict(r) for r in await cur.fetchall()]}


@router.get("/{work_id}/relations", summary="Relaciones actuales de una obra")
async def work_relations(work_id: int, db: Database = Depends(get_db)):
    out: dict[str, list[dict]] = {}
    async with db.connection() as conn, conn.cursor() as cur:
        for name, rel in RELATIONS.items():
            await cur.execute(rel["label_sql"], (work_id,))
            out[name] = [dict(r) for r in await cur.fetchall()]
    return {"work_id": work_id, "relations": out}


@router.post("/{work_id}/relations/{relation}", summary="Añade una relación a la obra")
async def add_relation(
    work_id: int,
    relation: str,
    payload: dict[str, Any] = Body(...),
    db: Database = Depends(get_db),
):
    rel = _relation(relation)
    cols = [rel["work_col"]]
    values: list[Any] = [work_id]
    for col in rel["cols"]:
        key = col
        short = col.replace("works_person_roles_", "").replace("work_", "").replace("_id", "")
        value = payload.get(key, payload.get(short, payload.get("id")))
        if value is None:
            raise HTTPException(status_code=422, detail=f"falta {short or key}")
        cols.append(col)
        values.append(value)
    placeholders = ", ".join(["%s"] * len(cols))
    names = ", ".join(f"`{c}`" for c in cols)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"INSERT IGNORE INTO `{rel['table']}` ({names}) VALUES ({placeholders})", values
        )
    return {"ok": True, "relation": relation, "added": rel["table"]}


@router.delete("/{work_id}/relations/{relation}", summary="Quita una relación de la obra")
async def remove_relation(
    work_id: int,
    relation: str,
    payload: dict[str, Any] = Body(...),
    db: Database = Depends(get_db),
):
    rel = _relation(relation)
    where = [f"`{rel['work_col']}` = %s"]
    values: list[Any] = [work_id]
    for col in rel["cols"]:
        short = col.replace("works_person_roles_", "").replace("work_", "").replace("_id", "")
        value = payload.get(col, payload.get(short, payload.get("id")))
        if value is None:
            raise HTTPException(status_code=422, detail=f"falta {short or col}")
        where.append(f"`{col}` = %s")
        values.append(value)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"DELETE FROM `{rel['table']}` WHERE {' AND '.join(where)}", values
        )
        deleted = cur.rowcount
    return {"ok": True, "relation": relation, "deleted": deleted}
