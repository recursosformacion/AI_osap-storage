from __future__ import annotations

import csv
from collections.abc import Iterator

from application.use_cases.import_pdmx import PdmxRow

RELATIVE_PATH_COLS = ["relative_path", "relativepath", "path", "file", "file_path", "filepath"]
ARCHIVE_NAME_COLS = ["archive", "archive_name", "tar", "name"]
ARCHIVE_URL_COLS = ["url", "archive_url", "source_url", "tar_url"]
LOGICAL_ID_COLS = ["logical_id", "key", "catalog_id", "id"]
COMPOSER_COLS = ["composer", "composer_name"]
TITLE_COLS = ["title", "song_name", "name"]


def _detect(header: list[str], candidates: list[str]) -> str | None:
    lowered = [h.strip().lower() for h in header]
    for candidate in candidates:
        if candidate in lowered:
            return header[lowered.index(candidate)]
    return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    if not v or v.lower() in ("na", "nan", "null", "none", "-"):
        return None
    return v


def read_pdmx_csv(
    path: str,
    *,
    relative_path_col: str | None = None,
    archive_name_col: str | None = None,
    archive_name: str | None = None,
    archive_url_col: str | None = None,
    archive_url: str | None = None,
    logical_id_col: str | None = None,
    composer_col: str | None = None,
    title_col: str | None = None,
) -> Iterator[PdmxRow]:
    """Lee un CSV de índice PDMX.

    El archive puede venir de una columna (`archive_name_col`) o ser constante
    (`archive_name`), que es lo habitual en PDMX real (mxl.tar.gz, pdf.tar.gz...).
    """
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])

        relative_path = relative_path_col or _detect(header, RELATIVE_PATH_COLS)
        if relative_path is None:
            raise ValueError(
                "PDMX CSV must have a relative_path column; found: " + ",".join(header)
            )
        archive_name_col = archive_name_col or _detect(header, ARCHIVE_NAME_COLS)
        if archive_name is None and archive_name_col is None:
            raise ValueError(
                "must provide archive name (column or --archive-name); found: " + ",".join(header)
            )
        archive_url_col = archive_url_col or _detect(header, ARCHIVE_URL_COLS)
        logical_id = logical_id_col or _detect(header, LOGICAL_ID_COLS)
        composer = composer_col or _detect(header, COMPOSER_COLS)
        title = title_col or _detect(header, TITLE_COLS)

        for record in reader:
            rel = _clean(record.get(relative_path))
            name = _clean(archive_name) or (
                _clean(record.get(archive_name_col)) if archive_name_col else None
            )
            if not rel or not name:
                continue
            row_url = archive_url or (
                _clean(record.get(archive_url_col)) if archive_url_col else None
            )
            yield PdmxRow(
                relative_path=rel,
                archive_name=name,
                archive_url=row_url,
                logical_id=_clean(record.get(logical_id)) if logical_id else None,
                composer=_clean(record.get(composer)) if composer else None,
                title=_clean(record.get(title)) if title else None,
            )
