"""Épocas (catálogo) para clasificar compositores. Solo lectura vía API.

`/api/admin/epochs` (admin) y `/api/v1/epochs` (público) devuelven el mismo catálogo:
id, título, años (pueden ser NULL) y descripción.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from infrastructure.db.connection import Database

from api.dependencies import get_db

router = APIRouter(prefix="/api/admin/epochs", tags=["admin-epochs"])
public_router = APIRouter(prefix="/api/v1/epochs", tags=["epochs"])


async def _list_epochs(db: Database) -> list[dict]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            # Prehistoria (sin año de inicio) va primero; luego por año ascendente.
            "SELECT id, title, year_start, year_end, description "
            "FROM epochs ORDER BY COALESCE(year_start, -1), title"
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get(
    "",
    summary="Listar épocas",
    description="Catálogo de épocas históricas de la música (id, título, años, descripción).",
)
async def list_epochs(db: Database = Depends(get_db)) -> list[dict]:
    return await _list_epochs(db)


@public_router.get(
    "",
    summary="Listar épocas (público)",
    description="Catálogo público de épocas históricas: id, título, años y descripción.",
)
async def list_epochs_public(db: Database = Depends(get_db)) -> list[dict]:
    return await _list_epochs(db)
