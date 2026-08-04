from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository

from infrastructure.importers.pdmx_csv import read_pdmx_csv


@dataclass(frozen=True)
class MirrorReport:
    csv: int
    archive_entries: int
    musicxml: int
    missing: int
    extra: int
    ok: bool


def _count_csv(csv_path: str, archive_name: str) -> int:
    return sum(
        1
        for _ in read_pdmx_csv(csv_path, relative_path_col="mxl", archive_name=archive_name)
    )


async def verify_mirror(
    archives: ArchiveRepository,
    entries: ArchiveEntryRepository,
    csv_path: str,
    archive_name: str,
) -> MirrorReport:
    """Compara CSV vs índice vs ficheros reales del mirror y reporta diferencias."""
    archive = await archives.get_by_name(archive_name)
    if archive is None or not archive.local_path:
        raise ValueError(f"archive '{archive_name}' not found or has no local_path")

    root = Path(archive.local_path)
    db_paths = set(await entries.list_relative_paths())

    # Recorre solo los directorios de nivel superior que referencia el índice
    # (p. ej. "mxl"), no todo el mirror (evita pdf/data/mid/metadata).
    top_dirs = {p.split("/")[1] for p in db_paths if p.startswith("./") and len(p.split("/")) > 2}
    disk_paths: set[str] = set()
    for top in top_dirs:
        base = root / top
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() == ".mxl":
                disk_paths.add("./" + path.relative_to(root).as_posix())

    csv_count = _count_csv(csv_path, archive_name)
    missing = len(db_paths - disk_paths)
    extra = len(disk_paths - db_paths)
    ok = (
        csv_count == len(db_paths) == len(disk_paths)
        and missing == 0
        and extra == 0
    )
    return MirrorReport(
        csv=csv_count,
        archive_entries=len(db_paths),
        musicxml=len(disk_paths),
        missing=missing,
        extra=extra,
        ok=ok,
    )
