"""Aplica propuestas de Wikidata sobre personas incompletas, solo campos vacíos.

No cambia nombres ni sobrescribe datos existentes. Añade el QID y los identificadores
a `persons_identity` y rellena años, nacionalidad, ficha e imagen cuando faltan.

Uso dev:
    .venv\\Scripts\\python.exe scripts/apply_wikidata_persons.py --dry-run
    .venv\\Scripts\\python.exe scripts/apply_wikidata_persons.py --apply
Por defecto solo aplica QID/identificadores (confianza >= 0.95); los matches por
nombre exacto quedan para revisión salvo `--include-name`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name  # noqa: E402

DEFAULT_DIR = ROOT / "data" / "wikidata_persons"
FIELDS = {
    "birth_year": "persons_birth_year",
    "death_year": "persons_death_year",
    "nationality": "persons_nationality",
    "description": "persons_biography_summary",
    "image": "persons_image_url",
}


def _conf() -> dict[str, Any]:
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("db") or {}
    return conf


def _latest_file(directory: Path) -> Path:
    files = list(directory.glob("proposals_*.json"))
    if not files:
        raise SystemExit(f"No hay propuestas en {directory}")
    return max(files, key=lambda path: path.stat().st_mtime)


def _apply_identity(cur: pymysql.cursors.Cursor, person: dict[str, Any], name: str) -> None:
    qid = str(person.get("qid") or "")
    if not qid:
        return
    cur.execute(
        "SELECT id FROM persons_identity WHERE persons_id=%s AND identity_type=%s "
        "AND identity_value=%s LIMIT 1",
        (person["persons_id"], "wikidata_qid", qid),
    )
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO persons_identity "
            "(persons_id, identity_name, identity_name_norm, identity_type, identity_value, "
            " identity_source, identity_is_anchor, identity_confidence, identity_retrieved_at) "
            "VALUES (%s, %s, %s, 'wikidata_qid', %s, 'wikidata', 0, %s, NOW(6))",
            (person["persons_id"], name, normalize_composer_name(name)[:128], qid,
             float(person.get("confidence") or 0)),
        )
    for identifier in person.get("identifiers") or []:
        kind = str(identifier.get("type") or "").lower()
        value = str(identifier.get("value") or "")
        if not kind or not value:
            continue
        cur.execute(
            "SELECT id FROM persons_identity WHERE persons_id=%s AND identity_type=%s "
            "AND identity_value=%s LIMIT 1",
            (person["persons_id"], kind, value),
        )
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO persons_identity "
                "(persons_id, identity_name, identity_name_norm, identity_type, identity_value, "
                " identity_source, identity_is_anchor, identity_confidence, identity_retrieved_at) "
                "VALUES (%s, %s, %s, %s, %s, 'wikidata', 0, %s, NOW(6))",
                (person["persons_id"], name, normalize_composer_name(name)[:128], kind, value,
                 float(person.get("confidence") or 0)),
            )


def _proposal_rows(path: Path, include_name: bool, min_confidence: float) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for item in data:
        method = str(item.get("match_method") or "")
        confidence = float(item.get("confidence") or 0)
        if not item.get("qid") or confidence < min_confidence:
            continue
        if not include_name and not (method == "wikidata_qid" or method.startswith("identifier:")):
            continue
        rows.append(item)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=None)
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-name", action="store_true")
    ap.add_argument("--min-confidence", type=float, default=0.95)
    ap.add_argument("--report", type=Path, default=ROOT / "data" / "wikidata_persons_apply.csv")
    ap.add_argument("--allow-prod", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        args.dry_run = True
    conf = _conf()
    if conf.get("host") not in {"127.0.0.1", "localhost"} and not args.allow_prod:
        raise SystemExit("rechazado: host no local; usa --allow-prod")

    path = args.file or _latest_file(args.dir)
    rows = _proposal_rows(path, args.include_name, args.min_confidence)
    if not rows:
        print("No hay propuestas aplicables.")
        return 0

    conn = pymysql.connect(
        host=conf.get("host", "127.0.0.1"), port=int(conf.get("port", 3306)),
        user=conf.get("user"), password=conf.get("password"), database=conf.get("name"),
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )
    report: list[dict[str, Any]] = []
    applied = unchanged = missing = 0
    try:
        with conn.cursor() as cur:
            for item in rows:
                cur.execute(
                    "SELECT * FROM persons WHERE persons_id=%s", (item["persons_id"],)
                )
                current = cur.fetchone()
                if current is None:
                    missing += 1
                    report.append({"persons_id": item["persons_id"], "status": "missing"})
                    continue
                changes: dict[str, Any] = {}
                for source, column in FIELDS.items():
                    value = item.get(source)
                    if value in (None, "", []):
                        continue
                    existing = current.get(column)
                    if existing not in (None, "", []):
                        continue
                    changes[column] = str(value) if source in {"birth_year", "death_year"} else value
                changed = bool(changes)
                if args.apply:
                    if changes:
                        sets = ", ".join(f"{col}=%s" for col in changes)
                        cur.execute(
                            f"UPDATE persons SET {sets}, persons_updated_at=NOW(6) WHERE persons_id=%s",
                            (*changes.values(), item["persons_id"]),
                        )
                    _apply_identity(cur, item, str(current.get("persons_name") or item.get("persons_name") or ""))
                if changed:
                    applied += 1
                else:
                    unchanged += 1
                report.append(
                    {
                        "persons_id": item["persons_id"],
                        "persons_name": current.get("persons_name"),
                        "status": "applied" if args.apply and changed else ("would_apply" if changed else "unchanged"),
                        "changed": ",".join(changes),
                        "qid": item.get("qid"),
                    }
                )
        if args.apply:
            conn.commit()
    finally:
        conn.close()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["persons_id", "persons_name", "status", "changed", "qid"])
        writer.writeheader()
        writer.writerows(report)
    print(f"propuestas={len(rows)} aplicadas={applied} sin_cambios={unchanged} no_encontradas={missing}")
    print(f"informe={args.report}")
    if not args.apply:
        print("DRY-RUN: no se ha escrito nada (usa --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())


