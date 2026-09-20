"""Importa el dump MARCXML de personas de RISM a un índice local (`rism_persons` +
`rism_person_names`).

Read-only respecto al catálogo propio: NO toca `persons` ni `persons_aliases`.

    .venv\\Scripts\\python.exe scripts/import_rism_persons.py --file G:\\rism\\person-latest.xml.gz
    .venv\\Scripts\\python.exe scripts/import_rism_persons.py --file ... --db osap-storage --dry-run
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


def _matchkey(name: str | None) -> str:
    return " ".join(sorted(normalize_composer_name(name).split()))


def _subfields(field, codes: str) -> list[str]:
    return [(s.text or "").strip() for s in field if s.get("code") in codes and (s.text or "").strip()]


def parse_record(record) -> dict | None:
    data = {"id": None, "name": None, "dates": None, "gnd": None, "viaf": None,
            "professions": [], "variants": []}
    for child in record:
        tag = child.get("tag")
        if child.tag == NS + "controlfield":
            if tag == "001":
                data["id"] = (child.text or "").strip()
        elif child.tag == NS + "datafield":
            if tag == "100":
                for s in child:
                    if s.get("code") == "a":
                        data["name"] = (s.text or "").strip()
                    elif s.get("code") == "d":
                        data["dates"] = (s.text or "").strip()
            elif tag == "400":
                value = next((s.text for s in child if s.get("code") == "a"), None)
                if value:
                    data["variants"].append(value.strip())
            elif tag == "024":
                source = next((s.text for s in child if s.get("code") == "2"), None)
                value = next((s.text for s in child if s.get("code") == "a"), None)
                if value:
                    if source == "DNB":
                        data["gnd"] = value.strip()
                    elif source == "VIAF":
                        data["viaf"] = value.strip()
            elif tag == "550":
                value = next((s.text for s in child if s.get("code") == "a"), None)
                if value:
                    data["professions"].append(value.strip())
    return data if data["id"] and data["name"] else None


def run(path: Path, db_name: str, dry_run: bool) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=db_name, charset="utf8mb4",
                           autocommit=False)
    persons: list[tuple] = []
    names: list[tuple] = []
    total = 0
    variants_total = 0

    def flush() -> None:
        nonlocal persons, names
        if dry_run or not persons:
            persons, names = [], []
            return
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO rism_persons (rism_person_id, rism_name, rism_dates, "
                "rism_professions, rism_is_composer, rism_gnd, rism_viaf, rism_n_variants) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                persons,
            )
            cur.executemany(
                "INSERT INTO rism_person_names (rism_person_id, rism_person_names_name, "
                "rism_person_names_normalized, rism_person_names_matchkey, rism_person_names_type) "
                "VALUES (%s,%s,%s,%s,%s)",
                names,
            )
        conn.commit()
        persons, names = [], []

    if not dry_run:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE rism_person_names")
            cur.execute("TRUNCATE TABLE rism_persons")
        conn.commit()

    with gzip.open(path, "rb") as fh:
        for _event, elem in ElementTree.iterparse(fh, events=("end",)):
            if elem.tag != NS + "record":
                continue
            data = parse_record(elem)
            elem.clear()
            if data is None:
                continue
            total += 1
            variants = list(dict.fromkeys(data["variants"]))
            variants_total += len(variants)
            professions = "; ".join(sorted(set(data["professions"])))
            is_composer = 1 if any("compos" in p.lower() for p in data["professions"]) else 0
            persons.append((
                data["id"], data["name"][:512], (data["dates"] or None), professions[:512] or None,
                is_composer, data["gnd"], data["viaf"], len(variants),
            ))
            for name, kind in [(data["name"], "main"), *[(v, "variant") for v in variants]]:
                names.append((
                    data["id"], name[:512], normalize_composer_name(name)[:191],
                    _matchkey(name)[:191], kind,
                ))
            if len(persons) >= BATCH:
                flush()
                print(f"  {total} personas...", flush=True)
    flush()
    conn.close()
    print(f"personas RISM: {total} | variantes: {variants_total} | db: {db_name} "
          f"| dry_run={dry_run}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=Path(r"G:\rism\person-latest.xml.gz"))
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.file, args.db, args.dry_run)


if __name__ == "__main__":
    main()
