"""Búsqueda sobre el corpus CPDL, que ahora vive en `works` (origin='CPDL').

Endpoints de SOLO LECTURA. El voicing (normalizado) ES la formación vocal: catálogo
`ensembles` relacionado con la obra en `work_ensembles` (`ensemble_voices` da la
composición en voces).
"""

from __future__ import annotations

from urllib.parse import quote_plus

from application.services.cpdl_voicing import normalize_term
from fastapi import APIRouter, Depends, HTTPException, Query
from infrastructure.config import Settings
from infrastructure.db.connection import Database

from api.dependencies import get_db, get_settings

router = APIRouter(prefix="/api/v1/cpdl", tags=["cpdl"])

# Compositor: primera persona con rol 1 enlazada a la obra.
_COMPOSER = (
    "(SELECT p.persons_name FROM works_person_roles r "
    " JOIN persons p ON p.persons_id = r.works_person_roles_person_id "
    " WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1 "
    " ORDER BY r.works_person_roles_order, r.works_person_roles_id LIMIT 1)"
)
# Voicing normalizado de la obra: su formación vocal (`ensembles` vía `work_ensembles`).
_VOICING = (
    "(SELECT GROUP_CONCAT(DISTINCT e.ensembles_code ORDER BY e.ensembles_code SEPARATOR ', ') "
    " FROM work_ensembles we JOIN ensembles e ON e.id = we.ensembles_id "
    " WHERE we.works_id = w.id)"
)
# Filtro por voicing: código de conjunto (o voz suelta) con coincidencia exacta.
_VOICING_MATCH = (
    "EXISTS (SELECT 1 FROM work_ensembles we JOIN ensembles e ON e.id = we.ensembles_id "
    " WHERE we.works_id = w.id AND UPPER(e.ensembles_code) {op} ({ph})) "
    "OR EXISTS (SELECT 1 FROM work_voices wv JOIN voices v ON v.id = wv.voices_id "
    " WHERE wv.works_id = w.id AND UPPER(v.voices_name) {op} ({ph}))"
)


def _row_out(row: dict) -> dict:
    title = row["title"]
    raw_terms = row.get("voicing")
    terms: list[str] = []
    if isinstance(raw_terms, str):
        terms = [t.strip() for t in raw_terms.split(",") if t.strip()]
    return {
        "id": row["id"],
        "page_title": title,
        "title": title,
        "composer": row.get("composer") or "",
        "catalogue_hint": row.get("catalogue_hint"),
        "voicing": terms,
        "voicing_terms": terms,
        "page_url": "https://www.cpdl.org/wiki/index.php?title=" + quote_plus(str(title)),
    }


async def _fetch(db: Database, where: str, params: list, limit: int, offset: int) -> list[dict]:
    sql = (
        f"SELECT w.id, w.works_title AS title, w.works_catalogue AS catalogue_hint, "
        f"{_VOICING} AS voicing, {_COMPOSER} AS composer "
        f"FROM works w WHERE w.works_origin = 'CPDL' AND {where} "
        f"ORDER BY w.works_title LIMIT %s OFFSET %s"
    )
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, [*params, limit, offset])
        return [_row_out(dict(r)) for r in await cur.fetchall()]


@router.get(
    "/search",
    summary="Buscar obras CPDL por voicing y/o texto",
    description="Busca en el corpus CPDL (`works.works_origin='CPDL'`). `voicing` es un "
    "término normalizado exacto (p. ej. SATB, SSATB, EQUAL VOICES); `q` busca por título "
    "o catálogo. Al menos uno de los dos es obligatorio.",
)
async def search_cpdl(
    voicing: list[str] | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []

    terms = [normalize_term(v) for v in (voicing or []) if v and v.strip()]
    terms = [t for t in terms if t]
    if terms:
        ph = ", ".join(["%s"] * len(terms))
        clauses.append("(" + _VOICING_MATCH.format(op="IN", ph=ph) + ")")
        params.extend([*terms, *terms])
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(w.works_title LIKE %s OR w.works_catalogue LIKE %s)")
        params.extend([like, like])
    if not clauses:
        raise HTTPException(status_code=422, detail="indica `voicing`, `q` o ambos")

    return await _fetch(db, " AND ".join(clauses), params, limit, offset)


@router.get(
    "/voicing/{term}",
    summary="Obras CPDL con un voicing exacto",
    description="Devuelve las obras CPDL cuyo voicing (normalizado) contiene el término exacto.",
)
async def pages_by_voicing(
    term: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    norm = normalize_term(term)
    if not norm:
        raise HTTPException(status_code=422, detail="término de voicing vacío")
    where = _VOICING_MATCH.format(op="=", ph="%s")
    return await _fetch(db, where, [norm, norm], limit, offset)
