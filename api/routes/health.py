from __future__ import annotations

from fastapi import APIRouter, Depends
from infrastructure.container import Container
from infrastructure.db.connection import Database

from api.dependencies import get_container, get_db

router = APIRouter(tags=["health"])


@router.get(
    "/api/v1/health",
    summary="Health check",
    description="Estado de la API, conexión a la base de datos y repositorio, con contadores.",
)
async def health(
    db: Database = Depends(get_db),
    container: Container = Depends(get_container),
) -> dict:
    checks: dict[str, bool] = {"database": False, "repository": False}
    try:
        async with db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1")
        checks["database"] = True
    except Exception:
        checks["database"] = False

    counts: dict[str, int] = {}
    try:
        counts = {
            "archives": await container.archive_repo.count(),
            "entries": await container.archive_entry_repo.count_total(),
            "files": await container.file_repo.count(),
            "locations": await container.location_repo.count(),
        }
        checks["repository"] = True
    except Exception:
        checks["repository"] = False

    status = "ok" if all(checks.values()) else "degraded"
    return {"status": status, "checks": checks, "counts": counts}
