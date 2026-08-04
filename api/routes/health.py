from __future__ import annotations

from fastapi import APIRouter, Depends
from infrastructure.db.connection import Database

from api.dependencies import get_db

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
async def health(db: Database = Depends(get_db)) -> dict[str, str]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT 1")
    return {"status": "ok"}
