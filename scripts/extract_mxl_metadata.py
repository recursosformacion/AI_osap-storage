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
from xml.etree import ElementTree as ET

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


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = _xml_text(archive)
    except (zipfile.BadZipFile, OSError, KeyError):
        return {"error": "no_mxl"}
    if not xml:
        return {"error": "no_xml"}

    creators: list[dict[str, str]] = []
    part_names: list[str] = []
    instruments: list[str] = []
    credits: list[str] = []
    keys: list[str] = []
    times: list[str] = []
    voices: set[str] = set()
    staves: set[str] = set()
    measures = 0
    notes = 0
    parts = 0
    midi_programs: list[str] = []
    lyrics = 0
    tempo = None
    work_number = None
    opus = None
    movement_number = None
    software = None
    encoding_date = None
    source = None
    rights = None
    try:
        root = ET.fromstring(xml)
        for elem in root.iter():
            tag = _local(elem.tag)
            text = _text(elem.text)
            if tag == "creator" and text:
                creators.append({"type": str(elem.get("type") or ""), "name": text})
            elif tag == "part-name" and text:
                part_names.append(text)
            elif tag == "instrument-name" and text:
                instruments.append(text)
            elif tag == "credit-words" and text:
                credits.append(text)
            elif tag == "source" and text:
                source = text
            elif tag == "rights" and text:
                rights = text
            elif tag == "work-number" and text:
                work_number = text
            elif tag == "opus" and text:
                opus = text
            elif tag == "movement-number" and text:
                movement_number = text
            elif tag == "software" and text:
                software = text
            elif tag == "encoding-date" and text:
                encoding_date = text
            elif tag in {"fifths", "mode"} and text:
                keys.append(text)
            elif tag in {"beats", "beat-type"} and text:
                times.append(text)
            elif tag == "voice" and text:
                voices.add(text)
            elif tag == "staves" and text:
                staves.add(text)
            elif tag == "measure":
                measures += 1
            elif tag == "part":
                parts += 1
            elif tag == "midi-program" and text:
                midi_programs.append(text)
            elif tag == "note":
                notes += 1
            elif tag == "lyric":
                lyrics += 1
            elif tag == "sound" and elem.get("tempo"):
                tempo = elem.get("tempo")
            elif tag == "per-minute" and text:
                tempo = tempo or text
        title = None
        for elem in root.iter():
            if _local(elem.tag) in {"movement-title", "work-title"}:
                title = _text(elem.text) or title
                if title:
                    break
    except ET.ParseError:
        title = _text((TITLE_RE.search(xml) or [None, None])[1]) if TITLE_RE.search(xml) else None
        creators = [
            {
                "type": "composer" if COMPOSER_RE.search(xml) else "",
                "name": _text(x) or "",
            }
            for x in CREATOR_RE.findall(xml)
        ]
        source = _text((SOURCE_RE.search(xml) or [None, None])[1]) if SOURCE_RE.search(xml) else None
        rights = _text((RIGHTS_RE.search(xml) or [None, None])[1]) if RIGHTS_RE.search(xml) else None

    composers = [c["name"] for c in creators if c["type"].lower() == "composer"]
    lyricists = [c["name"] for c in creators if c["type"].lower() in {"lyricist", "poet", "text"}]
    arrangers = [c["name"] for c in creators if "arrang" in c["type"].lower()]
    instrumentation = list(dict.fromkeys(instruments or part_names))
    if not instrumentation and midi_programs:
        gm = {
            "1": "Piano",
            "41": "Violín",
            "42": "Viola",
            "43": "Violonchelo",
            "44": "Contrabajo",
            "57": "Trompeta",
            "58": "Trombón",
            "59": "Tuba",
            "65": "Saxofón",
            "69": "Oboe",
            "71": "Fagot",
            "72": "Clarinete",
            "74": "Flauta",
            "76": "Flautín",
        }
        instrumentation = list(dict.fromkeys(gm.get(p, f"MIDI {p}") for p in midi_programs))
    has_lyrics = lyrics > 0
    lower = " ".join(part_names + instruments + instrumentation).casefold()
    if all(x in lower for x in ("soprano", "alto", "tenor", "bass")):
        ensemble = "SATB"
    elif "string quartet" in lower:
        ensemble = "String quartet"
    elif "orchestra" in lower:
        ensemble = "Orchestra"
    elif "choir" in lower or "chorus" in lower:
        ensemble = "Choir"
    elif "piano" in lower:
        ensemble = "Piano"
    elif has_lyrics and parts >= 2:
        ensemble = "Vocal ensemble"
    else:
        ensemble = None
    return {
        "xml_title": title,
        "composer": composers[0] if composers else None,
        "creators": [c for c in creators if c["name"]],
        "lyricist": lyricists[0] if lyricists else None,
        "arranger": arrangers[0] if arrangers else None,
        "source": source,
        "rights": rights,
        "credits": credits[:5],
        "work_number": work_number,
        "opus": opus,
        "movement_number": movement_number,
        "software": software,
        "encoding_date": encoding_date,
        "instrumentation": instrumentation,
        "ensemble_guess": ensemble,
        "keys": keys[:4],
        "time_signatures": list(dict.fromkeys(times)),
        "parts_count": parts,
        "measures": measures,
        "notes": notes,
        "voices": sorted(voices),
        "staves": sorted(staves),
        "midi_programs": midi_programs,
        "has_lyrics": has_lyrics,
        "tempo": tempo,
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
    fields = [
        "work_id",
        "current_title",
        "xml_title",
        "composer",
        "lyricist",
        "arranger",
        "creators",
        "source",
        "rights",
        "credits",
        "work_number",
        "opus",
        "movement_number",
        "software",
        "encoding_date",
        "instrumentation",
        "ensemble_guess",
        "keys",
        "time_signatures",
        "parts_count",
        "measures",
        "notes",
        "voices",
        "staves",
        "midi_programs",
        "has_lyrics",
        "tempo",
        "file",
        "error",
    ]
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

