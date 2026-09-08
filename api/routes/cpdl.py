"""Búsqueda sobre el corpus CPDL (cpdl_pages) por voicing y/o texto.

Endpoints de SOLO LECTURA sobre el corpus independiente CPDL. Devuelven páginas CPDL
(título, compositor, voicing original, URL wiki). NO tocan `works` ni crean obras:
la fusión con Works es responsabilidad de la capa de resultados (osap-api).
"""

from __future__ import annotations

from urllib.parse import quote_plus

from application.services.cpdl_voicing import normalize_term
from fastapi import APIRouter, Depends, HTTPException, Query
from infrastructure.config import Settings
from infrastructure.db.connection import Database

from api.dependencies import get_db, get_settings

router = APIRouter(prefix="/api/v1/cpdl", tags=["cpdl"])


def _row_out(row: dict, settings: Settings) -> dict:
    return {
        "id": row["id"],
        "page_title": row["page_title"],
        "title": row["title"],
        "composer": row["composer"],
        "catalogue_hint": row["catalogue_hint"],
        "voicing": row["voicing"],
        "voicing_terms": [t for t in (row.get("terms") or "").split(", ") if t],
        "page_url": "https://www.cpdl.org/wiki/index.php?title=" + quote_plus(str(row["page_title"])),
    }


@router.get(
    "/search",
    summary="Buscar páginas CPDL por voicing y/o texto",
    description="Busca en el corpus CPDL (independiente). `voicing` es un término "
    "normalizado exacto (p. ej. SATB, STTB, AATB, ATTB); `q` busca por título, "
    "compositor, catálogo o página. Al menos uno de los dos es obligatorio.",
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

    voice_terms = [normalize_term(v) for v in (voicing or []) if v and v.strip()]
    if voice_terms:
        # Coincidencia EXACTA por token normalizado (nunca substring). Varios términos
        # se interpretan como OR (cualquiera de ellos), siempre sobre la MISMA página.
        clauses.append(
            f"EXISTS (SELECT 1 FROM cpdl_voicings tv "
            f"WHERE tv.cpdl_page_id = p.id AND tv.term IN ({', '.join(['%s'] * len(voice_terms))}))"
        )
        params.extend(voice_terms)
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(p.title LIKE %s OR p.composer LIKE %s OR p.catalogue_hint LIKE %s "
            "OR p.page_title LIKE %s)"
        )
        params.extend([like, like, like, like])
    if not clauses:
        raise HTTPException(status_code=422, detail="indica `voicing`, `q` o ambos")

    where = " AND ".join(clauses)
    sql = (
        "SELECT p.id, p.page_title, p.title, p.composer, p.catalogue_hint, p.voicing, "
        "COALESCE(GROUP_CONCAT(t.term ORDER BY t.term SEPARATOR ', '), '') AS terms "
        "FROM cpdl_pages p "
        "LEFT JOIN cpdl_voicings t ON t.cpdl_page_id = p.id "
        f"WHERE {where} "
        "GROUP BY p.id, p.page_title, p.title, p.composer, p.catalogue_hint, p.voicing "
        "ORDER BY p.title "
        "LIMIT %s OFFSET %s"
    )
    params.extend([limit, offset])
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    return [_row_out(dict(r), settings) for r in rows]


@router.get(
    "/voicing/{term}",
    summary="Páginas CPDL con un voicing exacto",
    description="Devuelve las páginas CPDL cuyo conjunto de voicings contiene el término "
    "normalizado exacto (case-insensitive). Una página con varios voicings aparece una "
    "sola vez.",
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
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT p.id, p.page_title, p.title, p.composer, p.catalogue_hint, p.voicing, "
            "COALESCE(GROUP_CONCAT(t.term ORDER BY t.term SEPARATOR ', '), '') AS terms "
            "FROM cpdl_pages p "
            "JOIN cpdl_voicings t ON t.cpdl_page_id = p.id AND t.term = %s "
            "GROUP BY p.id, p.page_title, p.title, p.composer, p.catalogue_hint, p.voicing "
            "ORDER BY p.title "
            "LIMIT %s OFFSET %s",
            (norm, limit, offset),
        )
        rows = await cur.fetchall()
    return [_row_out(dict(r), settings) for r in rows]
