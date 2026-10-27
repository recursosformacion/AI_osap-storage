"""Extrae titulo y compositor de los MXL locales, sin escribir en la BD.

Recorre works_resources -> files -> storage_locations, abre el MXL, lee el MusicXML interno
y extrae movement-title/work-title, creator type="composer", poeta y source. Genera propuestas
JSON/CSV en data/mxl_metadata/.

Uso:
    .venv\\Scripts\\python.exe scripts/extract_mxl_metadata.py --limit 1000
    .venv\\Scripts\\python.exe scripts/extract_mxl_metadata.py --limit 0 --out ...
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
STORAGE = Path(r"G:\osap-storage")
OUT_DIR = ROOT / "data" / "mxl_metadata"
TITLE_RE = re.compile(r"<(?:movement-title|work-title)>(.*?)</(?:movement-title|work-title)>", re.S | re.I)
COMPOSER_RE = re.compile(r'<creator[^>]*type="composer"[^>]*>(.*?)</creator>', re.S | re.I)
CREATOR_RE = re.compile(r"<creator[^>]*>(.*?)</creator>", re.S | re.I)
SOURCE_RE = re.compile(r"<source>(.*?)</source>", re.S | re.I)
RIGHTS_RE = re.compile(r"<rights>(.*?)</rights>", re.S | re.I)
ROOTFILE_RE = re.compile(r'full-path="([^"]+)"', re.I)


def _db():
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    return pymysql.connect(
        host=conf["host"],
        port=conf["port"],
        user=conf["user"],
        password=conf["password"],
        database=conf["name"],
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


def _text(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip() or None


def _xml_text(archive: zipfile.ZipFile) -> str | None:
    names = archive.namelist()
    rootfile = None
    if "META-INF/container.xml" in names:
        container = archive.read("META-INF/container.xml").decode("utf-8", "replace")
        match = ROOTFILE_RE.search(container)
        if match and match.group(1) in names:
            rootfile = match.group(1)
    if rootfile is None:
        rootfile = next(
            (name for name in names if name.lower().endswith(".xml") and not name.startswith("META-INF")),
            None,
        )
    return archive.read(rootfile).decode("utf-8", "replace") if rootfile else None


def _path(object_key: str | None, name: str | None) -> Path | None:
    if object_key:
        candidate = STORAGE / object_key.replace("./", "", 1)
        if candidate.exists():
            return candidate
    if name:
        matches = list(STORAGE.glob(f"**/{name}"))
        if matches:
            return matches[0]
    return None


def _extract(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = _xml_text(archive)
    except (zipfile.BadZipFile, OSError, KeyError):
        return {"error": "no_mxl"}
    if not xml:
        return {"error": "no_xml"}
    creators = [_text(x) for x in CREATOR_RE.findall(xml)]
    return {
        "xml_title": _text((TITLE_RE.search(xml) or [None, None])[1]) if TITLE_RE.search(xml) else None,
        "composer": _text((COMPOSER_RE.search(xml) or [None, None])[1]) if COMPOSER_RE.search(xml) else None,
        "creators": [c for c in creators if c],
        "source": _text((SOURCE_RE.search(xml) or [None, None])[1]) if SOURCE_RE.search(xml) else None,
        "rights": _text((RIGHTS_RE.search(xml) or [None, None])[1]) if RIGHTS_RE.search(xml) else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "proposals.json")
    args = ap.parse_args()
    sql = """
        SELECT wr.works_resources_work_id AS work_id, wr.works_resources_file_id AS file_id,
               wr.works_resources_type AS resource_type, f.name AS file_name,
               sl.object_key, w.works_title
        FROM works_resources wr
        JOIN files f ON f.id = wr.works_resources_file_id
        JOIN storage_locations sl ON sl.file_id = f.id
        JOIN works w ON w.id = wr.works_resources_work_id
        WHERE LOWER(wr.works_resources_type) IN ('mxl', 'musicxml')
        ORDER BY wr.id
    """
    params: list[Any] = []
    if args.limit:
        sql += " LIMIT %s OFFSET %s"
        params = [args.limit, args.offset]
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()
    proposals: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        if row["work_id"] in seen:
            continue
        seen.add(row["work_id"])
        path = _path(row.get("object_key"), row.get("file_name"))
        data = _extract(path) if path else {"error": "file_not_found"}
        proposals.append(
            {
                "work_id": row["work_id"],
                "current_title": row.get("works_title"),
                "file": str(path) if path else None,
                **data,
            }
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = args.out.with_suffix(".csv")
    fields = ["work_id", "current_title", "xml_title", "composer", "creators", "source", "rights", "file", "error"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in proposals:
            writer.writerow({key: row.get(key) for key in fields})
    with_title = sum(1 for r in proposals if r.get("xml_title"))
    with_composer = sum(1 for r in proposals if r.get("composer"))
    errors = sum(1 for r in proposals if r.get("error"))
    print(f"obras={len(proposals)} con_titulo={with_title} con_compositor={with_composer} errores={errors}")
    print(f"json={args.out}")
    print(f"csv={csv_path}")
    print("No se ha escrito en la BD.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
