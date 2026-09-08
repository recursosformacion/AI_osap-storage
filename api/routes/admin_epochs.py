"""Épocas (catálogo) para clasificar compositores. Solo lectura vía API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from infrastructure.db.connection import Database

from api.dependencies import get_db

router = APIRouter(prefix="/api/admin/epochs", tags=["admin-epochs"])


@router.get(
    "",
    summary="Listar épocas",
    description="Catálogo de épocas históricas de la música (id, título, años, descripción).",
)
async def list_epochs(db: Database = Depends(get_db)) -> list[dict]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, title, year_start, year_end, description "
            "FROM epochs ORDER BY year_start IS NULL, year_start, title"
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
