"""Importa el dump MARCXML de fuentes RISM a un índice local COMPLETO
(`rism_sources` + `rism_source_links`).

Read-only respecto al catálogo propio: NO toca `works`, `representations` ni `persons`.

    .venv\\Scripts\\python.exe scripts/import_rism_sources.py --file G:\\rism\\source-latest.xml.gz
    .venv\\Scripts\\python.exe scripts/import_rism_sources.py --db osap-storage --dry-run
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import sys
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name  # noqa: E402

NS = "{http://www.loc.gov/MARC21/slim}"
BATCH = 2000
PROGRESS = 200000

SOURCE_COLUMNS = (
    "rism_source_id, rism_composer_person_id, rism_composer_name, rism_composer_dates, "
    "rism_reliability, rism_uniform_title, rism_title, rism_language, rism_shelfmark, "
    "rism_is_anonymous, rism_has_incipit, rism_uniform_title_norm, rism_title_norm, "
    "rism_source_type, rism_subjects, rism_notes, rism_institution_id, "
    "rism_standard_title_id, rism_other_persons, rism_incipit_count"
)
SOURCE_PLACEHOLDERS = ",".join(["%s"] * 20)


def _subfields(field, codes: str) -> list[str]:
    return [
        (s.text or "").strip()
        for s in field
        if s.get("code") in codes and (s.text or "").strip()
    ]


def parse_record(record) -> tuple[dict, list[tuple]]:
    data = {
        "source_id": None, "composer_person_id": None, "composer_name": None,
        "composer_dates": None, "reliability": None, "uniform_title": None, "title": None,
        "language": None, "shelfmark": None, "is_anonymous": 0, "has_incipit": 0,
        "source_type": None, "subjects": [], "notes": [], "institution_id": None,
        "standard_title_id": None, "other_persons": [], "incipit_count": 0,
    }
    links: list[tuple] = []
    for child in record:
        tag = child.get("tag")
        if child.tag == NS + "controlfield":
            if tag == "001":
                data["source_id"] = (child.text or "").strip()
            continue
        if child.tag != NS + "datafield":
            continue

        if tag == "100":
            for s in child:
                code = s.get("code")
                if code == "a":
                    data["composer_name"] = (s.text or "").strip()
                elif code == "d":
                    data["composer_dates"] = (s.text or "").strip()
                elif code == "j":
                    data["reliability"] = (s.text or "").strip()
                elif code == "0":
                    data["composer_person_id"] = (s.text or "").strip()
        elif tag == "240":
            for s in child:
                if s.get("code") == "a" and data["uniform_title"] is None:
                    data["uniform_title"] = (s.text or "").strip()
                elif s.get("code") == "0":
                    data["standard_title_id"] = (s.text or "").strip()
        elif tag == "245":
            for s in child:
                if s.get("code") == "a" and data["title"] is None:
                    data["title"] = (s.text or "").strip()
        elif tag == "041":
            values = _subfields(child, "a")
            if values:
                data["language"] = values[0]
        elif tag == "852":
            a_vals = _subfields(child, "a")
            c_vals = _subfields(child, "c")
            x_vals = _subfields(child, "x")
            if a_vals:
                data["shelfmark"] = a_vals[0]
            if c_vals:
                data["shelfmark"] = (
                    f"{data['shelfmark']} {c_vals[0]}" if data["shelfmark"] else c_vals[0]
                )
            if x_vals:
                data["institution_id"] = x_vals[0]
        elif tag == "031":
            data["has_incipit"] = 1
            data["incipit_count"] += 1
        elif tag == "593":
            values = _subfields(child, "a")
            if values and data["source_type"] is None:
                data["source_type"] = values[0]
        elif tag == "650":
            data["subjects"].extend(_subfields(child, "a"))
        elif tag == "500":
            data["notes"].extend(_subfields(child, "a"))
        elif tag in ("700", "710"):
            names = _subfields(child, "a")
            relators = _subfields(child, "4") or _subfields(child, "e")
            if names:
                suffix = f" ({relators[0]})" if relators else ""
                data["other_persons"].append(names[0] + suffix)
        elif tag == "856":
            url = next((s.text.strip() for s in child
                        if s.get("code") == "u" and (s.text or "").strip()), None)
            if url:
                note = next((s.text.strip() for s in child
                             if s.get("code") == "z" and (s.text or "").strip()), None)
                links.append((data["source_id"], url[:1024], (note or "")[:255] or None,
                              child.get("ind1")))

    if not data["source_id"]:
        return {}, []
    if not data["composer_name"]:
        data["is_anonymous"] = 1
    return data, links


def run(path: Path, db_name: str, dry_run: bool) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=db_name, charset="utf8mb4",
                           autocommit=False)
    rows: list[tuple] = []
    link_rows: list[tuple] = []
    total = 0
    total_links = 0

    def flush() -> None:
        nonlocal rows, link_rows
        if dry_run:
            rows, link_rows = [], []
            return
        with conn.cursor() as cur:
            if rows:
                cur.executemany(
                    f"INSERT INTO rism_sources ({SOURCE_COLUMNS}) VALUES ({SOURCE_PLACEHOLDERS})",
                    rows,
                )
            if link_rows:
                cur.executemany(
                    "INSERT INTO rism_source_links "
                    "(rism_source_id, rism_source_links_url, rism_source_links_note, "
                    "rism_source_links_ind1) VALUES (%s,%s,%s,%s)",
                    link_rows,
                )
        conn.commit()
        rows, link_rows = [], []

    if not dry_run:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE rism_source_links")
            cur.execute("TRUNCATE TABLE rism_sources")
        conn.commit()

    with gzip.open(path, "rb") as fh:
        for _event, elem in ElementTree.iterparse(fh, events=("end",)):
            if elem.tag != NS + "record":
                continue
            data, links = parse_record(elem)
            elem.clear()
            if not data:
                continue
            total += 1
            total_links += len(links)
            rows.append((
                data["source_id"][:32],
                data["composer_person_id"][:32] if data["composer_person_id"] else None,
                data["composer_name"][:512] if data["composer_name"] else None,
                data["composer_dates"][:64] if data["composer_dates"] else None,
                data["reliability"][:32] if data["reliability"] else None,
                data["uniform_title"][:512] if data["uniform_title"] else None,
                data["title"][:1024] if data["title"] else None,
                data["language"][:64] if data["language"] else None,
                data["shelfmark"][:255] if data["shelfmark"] else None,
                data["is_anonymous"],
                data["has_incipit"],
                normalize_composer_name(data["uniform_title"])[:191] or None,
                normalize_composer_name(data["title"])[:191] or None,
                data["source_type"][:120] if data["source_type"] else None,
                ("; ".join(dict.fromkeys(data["subjects"]))[:1000]) or None,
                (" | ".join(data["notes"])[:2000]) or None,
                data["institution_id"][:32] if data["institution_id"] else None,
                data["standard_title_id"][:32] if data["standard_title_id"] else None,
                ("; ".join(dict.fromkeys(data["other_persons"]))[:1000]) or None,
                data["incipit_count"],
            ))
            link_rows.extend(links)
            if len(rows) >= BATCH:
                flush()
                print(f"  {total} fuentes ({total_links} enlaces)...", flush=True)
    flush()
    conn.close()
    print(f"fuentes RISM: {total} | enlaces 856: {total_links} | db: {db_name} | dry_run={dry_run}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=Path(r"G:\rism\source-latest.xml.gz"))
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.file, args.db, args.dry_run)


if __name__ == "__main__":
    main()
