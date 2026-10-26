"""Aplica a la BD las respuestas JSON del pipeline de obras.

- Lee `data/works_ai_out/json_works_lote_*.json`.
- Aplica solo cambios seguros (`work="sí"`, sin comentarios de duplicado/fusión/división).
- Actualiza `works` y las tablas de unión:
  `work_genres`, `work_ensembles`, `work_instruments`, `work_language`.
- No borra obras ni cambia `works_id`.
- `--replace-joins` reemplaza las listas de unión de la obra (por defecto solo añade).

Uso dev:
    .venv\\Scripts\\python.exe scripts/apply_works_ai_json.py --dry-run
    .venv\\Scripts\\python.exe scripts/apply_works_ai_json.py --apply
Producción:
    ... --apply --allow-prod
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "works_ai_out"
DELICATE = re.compile(r"duplic|fusion|merge|divid|split|dos obras|no es una obra|no es obra|persona",
                      re.IGNORECASE)
SCALAR = {
    "title": "works_title", "subtitle": "works_subtitle", "catalogue": "works_catalogue",
    "opus": "works_opus", "attr_type": "works_attr_type", "attribution_note": "works_attribution_note",
    "year": "works_year", "year_from": "works_year_from", "year_to": "works_year_to",
    "musical_key": "works_musical_key", "duration": "works_duration", "measures": "works_measures",
    "pages": "works_pages", "parts": "works_parts", "complexity": "works_complexity",
    "license": "works_license", "description": "works_description",
    "instrumentation": "works_instrumentation",
}
JOINS = {
    "genres": ("work_genres", "genres_id", "genres", "name"),
    "ensembles": ("work_ensembles", "ensembles_id", "ensembles", "ensembles_name"),
    "instruments": ("work_instruments", "instruments_id", "instruments", "name_en"),
    "languages": ("work_language", "languages_id", "languages", "languages_code"),
}


def _conf(args: argparse.Namespace) -> dict[str, Any]:
    if args.db_name:
        return {"host": args.db_host, "port": args.db_port, "user": args.db_user,
                "password": args.db_password, "database": args.db_name}
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("db") or {}
    return {"host": conf.get("host", "127.0.0.1"), "port": int(conf.get("port", 3306)),
            "user": conf.get("user"), "password": conf.get("password"),
            "database": conf.get("name")}


def _clean(value: object) -> object:
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def _values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value or "").strip()
    return [x.strip() for x in re.split(r"[;,]", text) if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=OUT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--replace-joins", action="store_true")
    ap.add_argument("--report", type=Path, default=ROOT / "docs" / "ai" / "works_ai_apply_report.csv")
    ap.add_argument("--allow-prod", action="store_true")
    ap.add_argument("--db-host")
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user")
    ap.add_argument("--db-password")
    ap.add_argument("--db-name")
    args = ap.parse_args()
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    conf = _conf(args)
    if conf["host"] not in {"127.0.0.1", "localhost"} and not args.allow_prod:
        raise SystemExit("rechazado: host no local; usa --allow-prod")
    if not args.apply:
        args.dry_run = True
    files = sorted(args.dir.glob("json_works_lote_*.json")) if args.dir.exists() else []
    print(f"ficheros: {len(files)}")
    conn = pymysql.connect(**conf, charset="utf8mb4", cursorclass=DictCursor)
    report: list[dict[str, Any]] = []
    applied = skipped = manual = missing = 0
    seen: set[str] = set()
    try:
        with conn.cursor() as cur:
            maps: dict[str, dict[str, int]] = {}
            for name, (_table, _col, source, column) in JOINS.items():
                cur.execute(f"SELECT id, LOWER({column}) AS k FROM {source}")  # noqa: S608
                maps[name] = {str(r["k"]): int(r["id"]) for r in cur.fetchall() if r["k"]}
            la_id = maps.get("languages", {}).get("la")
            if la_id:
                maps["languages"].setdefault("latin", la_id)
                maps["languages"].setdefault("lat", la_id)
            for path in files:
                data = json.loads(path.read_text(encoding="utf-8"))
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    wid = str(row.get("works_id") or "")
                    if not wid or wid in seen:
                        continue
                    seen.add(wid)
                    if args.limit and (applied + skipped + manual + missing) >= args.limit:
                        break
                    cur.execute("SELECT * FROM works WHERE id=%s", (wid,))
                    current = cur.fetchone()
                    if current is None:
                        missing += 1
                        report.append({"works_id": wid, "title": row.get("title"), "status": "missing"})
                        continue
                    work = str(row.get("work") or "").strip().lower()
                    comment = str(row.get("comentario") or "").strip()
                    if work not in {"sí", "si", "yes"}:
                        manual += 1
                        report.append({"works_id": wid, "title": row.get("title"), "status": "not_work", "reason": comment})
                        continue
                    if comment and DELICATE.search(comment):
                        manual += 1
                        report.append({"works_id": wid, "title": row.get("title"), "status": "manual", "reason": comment})
                        continue
                    changes: dict[str, Any] = {}
                    for key, column in SCALAR.items():
                        value = _clean(row.get(key))
                        if value in (None, "", []):
                            continue
                        if str(current.get(column) or "") == str(value):
                            continue
                        changes[column] = value
                    join_values: dict[str, list[int]] = {}
                    unknown: list[str] = []
                    for name, values in ((n, _values(row.get(n))) for n in JOINS):
                        ids: list[int] = []
                        for value in values:
                            found = maps[name].get(value.lower())
                            if found is not None:
                                ids.append(found)
                            else:
                                unknown.append(f"{name}:{value}")
                        if ids:
                            join_values[name] = list(dict.fromkeys(ids))
                    if not changes and not join_values:
                        skipped += 1
                        report.append({"works_id": wid, "title": row.get("title"), "status": "unchanged"})
                        continue
                    if args.apply:
                        if changes:
                            sets = ", ".join(f"{c}=%s" for c in changes)
                            cur.execute(f"UPDATE works SET {sets} WHERE id=%s", (*changes.values(), wid))  # noqa: S608
                        if args.replace_joins:
                            for name, (table, _col, _source, _column) in JOINS.items():
                                if name in join_values:
                                    cur.execute(f"DELETE FROM {table} WHERE works_id=%s", (wid,))  # noqa: S608
                        for name, ids in join_values.items():
                            table, col, _source, _column = JOINS[name]
                            for link_id in ids:
                                cur.execute(
                                    f"INSERT IGNORE INTO {table} (works_id, {col}) VALUES (%s,%s)",  # noqa: S608
                                    (wid, link_id))
                        applied += 1
                    else:
                        applied += 1
                    report.append({"works_id": wid, "title": row.get("title"),
                                   "status": "applied" if args.apply else "would_apply",
                                   "changed": ",".join(changes) + ((" joins:" + ",".join(join_values)) if join_values else ""),
                                   "unknown": "; ".join(unknown)})
                if args.limit and (applied + skipped + manual + missing) >= args.limit:
                    break
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["works_id", "title", "status", "reason", "changed", "unknown"])
        w.writeheader()
        w.writerows(report)
    print(f"aplicadas={applied} sin_cambios={skipped} manual={manual} no_encontradas={missing}")
    print(f"informe: {args.report}")
    if not args.apply:
        print("DRY-RUN: no se ha escrito nada (usa --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

