"""Clasificaciones (catálogos de referencia) — lectura pública.

Géneros, categorías e instrumentos y ensembles. Solo lectura; el mantenimiento se hace
desde las tablas admin correspondientes. `ensembles_description` y `catalog_description`
ya existen en el esquema.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from infrastructure.db.connection import Database

from api.dependencies import get_db

genres_router = APIRouter(prefix="/api/v1/genres", tags=["classifications"])
instrument_categories_router = APIRouter(
    prefix="/api/v1/instrument-categories", tags=["classifications"]
)
instruments_router = APIRouter(prefix="/api/v1/instruments", tags=["classifications"])
ensembles_router = APIRouter(prefix="/api/v1/ensembles", tags=["classifications"])


def _json_or_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


@genres_router.get(
    "",
    summary="Géneros musicales",
    description="Catálogo de géneros (macro-familia) con su descripción.",
)
async def list_genres(db: Database = Depends(get_db)) -> list[dict]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id, name, description FROM genres ORDER BY name")
        return [dict(r) for r in await cur.fetchall()]


@instrument_categories_router.get(
    "",
    summary="Categorías de instrumentos",
    description="Categorías raíz y subfamilias de instrumentos (dos niveles, parent_id).",
)
async def list_instrument_categories(db: Database = Depends(get_db)) -> list[dict]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, code, name, mb_type, parent_id, sort "
            "FROM instrument_categories ORDER BY sort, name"
        )
        return [dict(r) for r in await cur.fetchall()]


@instruments_router.get(
    "",
    summary="Instrumentos y voces",
    description="Instrumentos/voces/conjuntos con nombre en/es, alias y códigos IMSLP.",
)
async def list_instruments(db: Database = Depends(get_db)) -> list[dict]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, code, category_id, name_en, name_es, aliases, imslp_codes, clef, sort "
            "FROM instruments ORDER BY sort, name_es"
        )
        rows = [dict(r) for r in await cur.fetchall()]
    for row in rows:
        row["aliases"] = _json_or_none(row.get("aliases"))
        row["imslp_codes"] = _json_or_none(row.get("imslp_codes"))
    return rows


@ensembles_router.get(
    "",
    summary="Ensembles y formaciones",
    description="Ensembles/formaciones vocales e instrumentales con su descripción (si la tienen).",
)
async def list_ensembles(db: Database = Depends(get_db)) -> list[dict]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, ensembles_code AS code, ensembles_name AS name, "
            "ensembles_description AS description FROM ensembles ORDER BY ensembles_name"
        )
        return [dict(r) for r in await cur.fetchall()]
