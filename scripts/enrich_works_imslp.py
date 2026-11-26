"""Completa metadatos de obras IMSLP desde la plantilla wikitext de IMSLP.

IMSLP conserva en el wikitext de cada obra campos estructurados que la importación
no volcó a `works`: año de composición/publicación, instrumentación, opus, tonalidad,
estilo/época, etc. Este script los lee por lotes con la API de MediaWiki y rellena
solo campos vacíos, con cursor persistente para poder recorrer las ~266k obras IMSLP
en varias ejecuciones.

Uso:
    .venv/bin/python scripts/enrich_works_imslp.py --limit 100
    .venv/bin/python scripts/enrich_works_imslp.py --limit 100 --apply --allow-prod
    .venv/bin/python scripts/enrich_works_imslp.py --limit 5000 --sleep 0.7 --apply --allow-prod
"""

from __future__ import annotations

import argparse
import asyncio
import html as html_lib
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import PROJECT_ROOT, Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
API = "https://imslp.org/api.php"
BATCH = 20
STYLE_TO_EPOCH = {
    "medieval": 2,
    "renaissance": 3,
    "baroque": 4,
    "classical": 5,
    "romantic": 6,
    "early 20th century": 7,
    "modern": 7,
    "20th century": 7,
    "contemporary": 7,
    "post-1900": 7,
}
_FIELD_RE = re.compile(r"\|\s*([^=\n|]+?)\s*=\s*([^\n|}]*)")
_WIKI_LINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_TAGS = re.compile(r"<[^>]+>")


def _clean(value: str) -> str:
    value = _WIKI_LINK.sub(lambda m: m.group(2) or m.group(1), value or "")
    value = _TEMPLATE.sub(" ", value)
    value = _TAGS.sub(" ", value)
    value = html_lib.unescape(value)
    return re.sub(r"\s+", " ", value).strip(" ;,")


def _fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in _FIELD_RE.findall(content or ""):
        key = key.strip()
        if key and key not in fields:
            fields[key] = _clean(value)
    return fields


def _year(value: str) -> int | None:
    match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", value or "")
    if not match:
        return None
    year = int(match.group(1))
    return year if 1400 <= year <= datetime.now(UTC).year + 1 else None


def _epoch(style: str, year: int | None) -> int | None:
    low = (style or "").casefold()
    for key, epoch in STYLE_TO_EPOCH.items():
        if key in low:
            return epoch
    if year is None:
        return None
    if year <= 476:
        return 1
    if year <= 1450:
        return 2
    if year <= 1600:
        return 3
    if year <= 1750:
        return 4
    if year <= 1820:
        return 5
    if year <= 1900:
        return 6
    return 7


def _valid_text(value: str, limit: int) -> str | None:
    text = (value or "").strip()
    if not text or len(text) > limit or "{{" in text or "}}" in text or "<" in text:
        return None
    return text


def _imslp_title(url: str) -> str:
    parts = url.split("/wiki/", 1)
    if len(parts) != 2:
        return ""
    return unquote(parts[1]).replace("_", " ").strip()


def fetch_batch(titles: list[str]) -> dict[str, str]:
    if not titles:
        return {}
    try:
        response = httpx.get(
            API,
            params={
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "format": "json",
                "titles": "|".join(titles),
            },
            headers={"User-Agent": USER_AGENT},
            timeout=45,
            follow_redirects=True,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return {}
    result: dict[str, str] = {}
    normalized = {
        item.get("to"): item.get("from") for item in data.get("query", {}).get("normalized", [])
    }
    for page in data.get("query", {}).get("pages", {}).values():
        title = str(page.get("title") or "")
        revisions = page.get("revisions") or []
        if not revisions:
            continue
        revision = revisions[0]
        content = str(
            revision.get("*")
            or revision.get("slots", {}).get("main", {}).get("*")
            or ""
        )
        if content:
            result[title] = content
            original = normalized.get(title)
            if original:
                result[original] = content
    return result


def _cursor_path() -> Path:
    return PROJECT_ROOT / "var" / "imslp_works_cursor.txt"


def _read_cursor() -> int:
    path = _cursor_path()
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="ascii").strip() or 0)
    except ValueError:
        return 0


def _write_cursor(value: int) -> None:
    path = _cursor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(value), encoding="ascii")


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    db = Database(settings.model_copy(update={"db_name": args.db}))
    await db.connect()
    cursor = args.after if args.after is not None else _read_cursor()
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, works_title, works_source_url, works_year, works_opus, "
            "works_musical_key, works_instrumentation, works_epoch_id "
            "FROM works WHERE works_origin='IMSLP' AND works_source_url LIKE %s "
            "AND id > %s ORDER BY id LIMIT %s",
            ("https://imslp.org/wiki/%", cursor, args.limit),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        print("No hay obras IMSLP pendientes tras el cursor", cursor)
        return 0
    print(f"obras: {len(rows)} desde id>{cursor}")
    updates: list[tuple[Any, ...]] = []
    stats = {"year": 0, "instrumentation": 0, "opus": 0, "key": 0, "epoch": 0, "sin_datos": 0}
    samples: list[dict[str, Any]] = []
    last_success_id = cursor
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        title_map = {row["id"]: _imslp_title(str(row["works_source_url"])) for row in chunk}
        contents = fetch_batch([t for t in title_map.values() if t])
        if not contents:
            print("  lote sin respuesta de IMSLP; se detiene para reintentarlo después")
            break
        for row in chunk:
            content = contents.get(title_map[row["id"]], "")
            if not content:
                stats["sin_datos"] += 1
                continue
            fields = _fields(content)
            year = _year(fields.get("Year/Date of Composition", "")) or _year(
                fields.get("Year of First Publication", "")
            )
            style = fields.get("Piece Style", "")
            epoch = _epoch(style, year or (int(row["works_year"]) if row["works_year"] else None))
            instrumentation = _valid_text(fields.get("Instrumentation", ""), 500) or ""
            opus = _valid_text(fields.get("Opus/Catalogue Number", ""), 255) or ""
            key = _valid_text(fields.get("Key", ""), 255) or ""
            set_year = year if row["works_year"] is None and year else None
            set_inst = (
                instrumentation
                if not str(row["works_instrumentation"] or "").strip()
                and 0 < len(instrumentation) <= 500
                else None
            )
            set_opus = opus if not str(row["works_opus"] or "").strip() and len(opus) <= 255 else None
            set_key = key if not str(row["works_musical_key"] or "").strip() and len(key) <= 255 else None
            set_epoch = epoch if row["works_epoch_id"] is None and epoch else None
            if not any((set_year, set_inst, set_opus, set_key, set_epoch)):
                continue
            stats["year"] += bool(set_year)
            stats["instrumentation"] += bool(set_inst)
            stats["opus"] += bool(set_opus)
            stats["key"] += bool(set_key)
            stats["epoch"] += bool(set_epoch)
            updates.append((set_year, set_inst, set_opus, set_key, set_epoch, row["id"]))
            if len(samples) < 15:
                samples.append({
                    "id": row["id"],
                    "title": row["works_title"],
                    "year": set_year,
                    "instrumentation": set_inst,
                    "opus": set_opus,
                    "key": set_key,
                    "epoch": set_epoch,
                })
        last_success_id = max(row["id"] for row in chunk)
        if args.sleep:
            time.sleep(args.sleep)
    print({"candidatos": len(updates), **stats})
    for sample in samples:
        print(" ", sample)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = PROJECT_ROOT / "var" / f"imslp_works_{stamp}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"applied": args.apply, "stats": stats, "samples": samples}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("informe:", report)
    if not args.apply:
        print("DRY-RUN: usa --apply --allow-prod para escribir")
        await db.close()
        return 0
    if not args.allow_prod:
        print("--apply requiere --allow-prod")
        await db.close()
        return 1
    async with db.transaction() as conn, conn.cursor() as cur:
        await cur.executemany(
            "UPDATE works SET works_year=COALESCE(%s, works_year), "
            "works_instrumentation=COALESCE(%s, works_instrumentation), "
            "works_opus=COALESCE(%s, works_opus), "
            "works_musical_key=COALESCE(%s, works_musical_key), "
            "works_epoch_id=COALESCE(%s, works_epoch_id) WHERE id=%s",
            updates,
        )
    _write_cursor(last_success_id)
    print("aplicado; cursor:", last_success_id)
    await db.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="osap_storage")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after", type=int)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-prod", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

