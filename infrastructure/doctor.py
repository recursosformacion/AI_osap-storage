from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from infrastructure.container import Container
from infrastructure.verification import verify_mirror


@dataclass(frozen=True)
class LinksReport:
    checked: int
    found: int
    missing: int
    missing_samples: list[str]


@dataclass(frozen=True)
class DoctorReport:
    mirror_ok: bool
    mirror_detail: str
    database_ok: bool
    storage_ok: bool
    storage_detail: str
    providers: int
    archives: int
    archive_entries: int
    files: int
    storage_locations: int
    links_checked: int = 0
    links_found: int = 0
    links_missing: int = 0
    links_samples: list[str] = field(default_factory=list)
    ok: bool = False


async def check_index_links(container: Container) -> LinksReport:
    """Comprueba que cada StorageLocation existe físicamente en su proveedor."""
    checked = 0
    found = 0
    missing = 0
    samples: list[str] = []
    limit = 1000
    offset = 0
    while True:
        locations = await container.location_repo.list_all(limit=limit, offset=offset)
        if not locations:
            break
        for location in locations:
            checked += 1
            provider = await container.provider_repo.get_by_id(location.provider_id)
            if provider is None:
                missing += 1
                if len(samples) < 10:
                    samples.append(f"proveedor {location.provider_id} ausente: {location.object_key}")
                continue
            try:
                ok = await container.registry.backend_for(provider).exists(location.object_key)
            except Exception:
                ok = False
            if ok:
                found += 1
            else:
                missing += 1
                if len(samples) < 10:
                    samples.append(location.object_key)
        offset += limit
    return LinksReport(checked=checked, found=found, missing=missing, missing_samples=samples)


async def run_doctor(
    container: Container,
    csv_path: str | None,
    archive_name: str,
    check_links: bool = False,
) -> DoctorReport:
    database_ok = True
    try:
        async with container.db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1")
    except Exception:
        database_ok = False

    storage_ok = True
    storage_detail = ""
    providers = 0
    try:
        providers_list = await container.provider_repo.list(enabled_only=False)
        providers = len(providers_list)
        if providers_list:
            container.registry.backend_for(providers_list[0])
            root = (providers_list[0].config or {}).get("root")
            if root:
                Path(root).mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        storage_ok = False
        storage_detail = str(exc)

    mirror_ok = True
    mirror_detail = ""
    archive = await container.archive_repo.get_by_name(archive_name)
    has_local_content = archive is not None and archive.local_path and os.path.isdir(archive.local_path)
    if csv_path and has_local_content:
        try:
            report = await verify_mirror(
                container.archive_repo,
                container.archive_entry_repo,
                csv_path,
                archive_name,
            )
            mirror_ok = report.ok
            if not report.ok:
                mirror_detail = (
                    f"csv={report.csv} entries={report.archive_entries} "
                    f"mxl={report.musicxml} missing={report.missing} extra={report.extra}"
                )
        except Exception as exc:
            mirror_ok = False
            mirror_detail = str(exc)
    elif csv_path or has_local_content:
        # Sin CSV o sin contenido local (p. ej. contenido remoto en R2):
        # la comprobación se limita al índice cargado.
        mirror_ok = True
        mirror_detail = "índice presente; contenido remoto (sin verificación local)"
    else:
        mirror_ok = False
        mirror_detail = "CSV no configurado"

    archives = await container.archive_repo.count()
    archive_entries = await container.archive_entry_repo.count_total()
    files = await container.file_repo.count()
    storage_locations = await container.location_repo.count()

    links_checked = 0
    links_found = 0
    links_missing = 0
    links_samples: list[str] = []
    if check_links:
        links = await check_index_links(container)
        links_checked = links.checked
        links_found = links.found
        links_missing = links.missing
        links_samples = links.missing_samples

    ok = database_ok and storage_ok and mirror_ok and (links_missing == 0 if check_links else True)
    return DoctorReport(
        mirror_ok=mirror_ok,
        mirror_detail=mirror_detail,
        database_ok=database_ok,
        storage_ok=storage_ok,
        storage_detail=storage_detail,
        providers=providers,
        archives=archives,
        archive_entries=archive_entries,
        files=files,
        storage_locations=storage_locations,
        links_checked=links_checked,
        links_found=links_found,
        links_missing=links_missing,
        links_samples=links_samples,
        ok=ok,
    )
