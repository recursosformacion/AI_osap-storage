from __future__ import annotations

from application.use_cases.resolve_file import Resolution
from infrastructure.config import Settings


def build_resource_url(
    relative_path: str,
    file_id: int | None,
    settings: Settings,
) -> tuple[str | None, bool]:
    """Devuelve (url, available) para un recurso (representación)."""
    if settings.r2_serve_directly and settings.r2_public_url:
        parts = [settings.r2_public_url.rstrip("/")]
        prefix = settings.r2_path_prefix.strip("/")
        if prefix:
            parts.append(prefix)
        parts.append(relative_path.lstrip("./"))
        return "/".join(parts), True
    if file_id is not None:
        return f"{settings.public_base_url.rstrip('/')}/api/v1/files/{file_id}/content", True
    return None, False


def build_resolution_url(resolution: Resolution, settings: Settings) -> tuple[bool, str | None]:
    """Devuelve (available, url) para una resolución.

    Con repositorio R2 y serve_directly, la URL es del CDN (mismo árbol, con path_prefix).
    Si no, la URL apunta al contenido del propio servicio.
    """
    available = resolution.available
    url = None
    if resolution.found and settings.r2_serve_directly and settings.r2_public_url:
        path = (resolution.relative_path or "").lstrip("./")
        parts = [settings.r2_public_url.rstrip("/")]
        prefix = settings.r2_path_prefix.strip("/")
        if prefix:
            parts.append(prefix)
        parts.append(path)
        url = "/".join(parts)
        available = True
    elif resolution.available and resolution.file_id is not None:
        url = f"{settings.public_base_url.rstrip('/')}/api/v1/files/{resolution.file_id}/content"
    return available, url
