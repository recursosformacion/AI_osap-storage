"""Aplica propuestas de Wikidata a obras, solo campos vacios.

Por defecto solo aplica coincidencias de alta confianza por QID de compositor + titulo
(`composer_qid+title`). No cambia titulo ni compositor. Las propuestas por titulo
(`--title-only`) quedan fuera salvo `--include-title`.

Uso dev:
    .venv\\Scripts\\python.exe scripts/apply_wikidata_works.py --dry-run
    .venv\\Scripts\\python.exe scripts/apply_wikidata_works.py --apply
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "wikidata_works"
FIELDS = {
    "year": "works_year",
    "catalogue": "works_catalogue",
    "description": "works_description",
}


def _conf() -> dict[str, Any]:
    return ((yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("db") or {})


def _latest(directory: Path) -> Path:
    files = list(directory.glob("proposals_*.json"))
    if not files:
        raise SystemExit(f"No hay propuestas en {directory}")
    return max(files, key=lambda path: path.stat().st_mtime)


def _rows(path: Path, include_title: bool, min_confidence: float) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for item in data:
        if not item.get("qid") or float(item.get("confidence") or 0) < min_confidence:
            continue
        method = str(item.get("match_method") or "")
        if not include_title and method != "composer_qid+title":
            continue
        out.append(item)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=None)
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-title", action="store_true")
    ap.add_argument("--min-confidence", type=float, default=0.80)
    ap.add_argument("--report", type=Path, default=ROOT / "data" / "wikidata_works_apply.csv")
    ap.add_argument("--allow-prod", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        args.dry_run = True
    conf = _conf()
    if conf.get("host") not in {"127.0.0.1", "localhost"} and not args.allow_prod:
        raise SystemExit("rechazado: host no local; usa --allow-prod")

    path = args.file or _latest(args.dir)
    rows = _rows(path, args.include_title, args.min_confidence)
    if not rows:
        print("No hay propuestas aplicables.")
        return 0
    conn = pymysql.connect(
        host=conf.get("host", "127.0.0.1"), port=int(conf.get("port", 3306)),
        user=conf.get("user"), password=conf.get("password"), database=conf.get("name"),
        charset="utf8mb4", cursorclass=DictCursor,
    )
    report: list[dict[str, Any]] = []
    applied = unchanged = missing = 0
    try:
        with conn.cursor() as cur:
            for item in rows:
                cur.execute("SELECT * FROM works WHERE id=%s", (item["works_id"],))
                current = cur.fetchone()
                if current is None:
                    missing += 1
                    report.append({"works_id": item["works_id"], "status": "missing"})
                    continue
                changes: dict[str, Any] = {}
                for source, column in FIELDS.items():
                    value = item.get(source)
                    if value in (None, "", []):
                        continue
                    if current.get(column) not in (None, "", []):
                        continue
                    changes[column] = value
                if changes and args.apply:
                    sets = ", ".join(f"{col}=%s" for col in changes)
                    cur.execute(
                        f"UPDATE works SET {sets}, works_updated_at=NOW(6) WHERE id=%s",
                        (*changes.values(), item["works_id"]),
                    )
                if changes:
                    applied += 1
                else:
                    unchanged += 1
                report.append(
                    {
                        "works_id": item["works_id"],
                        "current_title": current.get("works_title"),
                        "status": "applied" if args.apply and changes else ("would_apply" if changes else "unchanged"),
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
        writer = csv.DictWriter(fh, fieldnames=["works_id", "current_title", "status", "changed", "qid"])
        writer.writeheader()
        writer.writerows(report)
    print(f"propuestas={len(rows)} aplicadas={applied} sin_cambios={unchanged} no_encontradas={missing}")
    print(f"informe={args.report}")
    if not args.apply:
        print("DRY-RUN: no se ha escrito nada (usa --apply)")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
