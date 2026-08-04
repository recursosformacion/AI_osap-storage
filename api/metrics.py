from __future__ import annotations

from application.use_cases.statistics import GetStatistics
from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from api.dependencies import GetStatisticsDep

router = APIRouter(tags=["metrics"])

HTTP_REQUESTS = Counter("osap_http_requests_total", "HTTP requests", ["method", "path"])
GAUGE_ARCHIVES = Gauge("osap_archives", "Archives")
GAUGE_ENTRIES = Gauge("osap_entries", "Archive entries")
GAUGE_FILES = Gauge("osap_files", "Files")
GAUGE_BYTES = Gauge("osap_repository_bytes", "Repository bytes")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", None) or request.url.path
        HTTP_REQUESTS.labels(request.method, path).inc()
        return response


@router.get("/metrics", include_in_schema=False)
async def metrics(uc: GetStatistics = Depends(GetStatisticsDep)) -> Response:
    stats = await uc.execute()
    GAUGE_ARCHIVES.set(stats.archives)
    GAUGE_ENTRIES.set(stats.entries)
    GAUGE_FILES.set(stats.files)
    GAUGE_BYTES.set(stats.bytes)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
