"""Incorpora a la BD las respuestas JSON de personas generadas por la IA.

Lee ficheros `json_personas_lote_*.json` que contengan `person`/`comentario` (por ejemplo
`data/ai_out/`) y aplica **solo cambios seguros** sobre la BD local:

- `person="sí"` y sin comentarios delicados: completa/corrige nombre, given/family/sort,
  años, resumen, época, referencias e imagen; marca reviewed.
- `person="no"` o comentarios de fusión/división/duplicado/segunda persona: **no escribe**;
  deja el registro en la cola de revisión.
- No borra ni oculta personas.

Uso dev:
    .venv\\Scripts\\python.exe scripts/apply_persons_ai_json.py --dry-run
    .venv\\Scripts\\python.exe scripts/apply_persons_ai_json.py --apply
Producción (en el servidor, con la BD de producción):
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
DATA = ROOT / "data"
OUT = DATA / "ai_out"
DELICATE = re.compile(
    r"fusion|merge|separ|split|duplic|dos personas|crear registro|unir|combinad|"
    r"segundo nombre|registro independiente|persona principal",
    re.IGNORECASE,
)
FIELDS = {
    "persons_name": "persons_name",
    "persons_givenname": "persons_givenname",
    "persons_familyname": "persons_familyname",
    "persons_sortname": "persons_sortname",
    "persons_birth_year": "persons_birth_year",
    "persons_death_year": "persons_death_year",
    "persons_biography_summary": "persons_biography_summary",
    "persons_biography_era": "persons_biography_era",
    "persons_biography_references": "persons_biography_references",
    "persons_image_url": "persons_image_url",
}


def _conf(args: argparse.Namespace) -> dict[str, Any]:
    if args.db_name:
        return {"host": args.db_host, "port": args.db_port, "user": args.db_user,
                "password": args.db_password, "database": args.db_name}
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("db") or {}
    return {"host": conf.get("host", "127.0.0.1"), "port": int(conf.get("port", 3306)),
            "user": conf.get("user"), "password": conf.get("password"),
            "database": conf.get("name")}


def _files(dirs: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for d in dirs:
        if not d.exists():
            continue
        for path in sorted(d.glob("json_personas_lote_*.json")):
            if path in seen:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, list) and any(isinstance(r, dict) and "person" in r for r in data):
                seen.add(path)
                out.append(path)
    return out


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dirs", nargs="*", default=[str(OUT), str(DATA)])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", type=Path, default=ROOT / "docs" / "ai" / "persons_ai_apply_report.csv")
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
        raise SystemExit("rechazado: host no local; usa --allow-prod de forma consciente")
    if int(conf.get("port", 0)) == 3307 and not args.allow_prod:
        raise SystemExit("rechazado: el puerto 3307 es el túnel de producción")
    if not args.apply:
        args.dry_run = True

    files = _files([Path(d) for d in args.dirs])
    print(f"ficheros con respuestas: {len(files)}")
    conn = pymysql.connect(**conf, charset="utf8mb4", cursorclass=DictCursor)
    rows_report: list[dict[str, Any]] = []
    applied = skipped = manual = missing = 0
    seen: set[str] = set()
    try:
        with conn.cursor() as cur:
            for path in files:
                data = json.loads(path.read_text(encoding="utf-8"))
                for row in data:
                    if not isinstance(row, dict) or "person" not in row:
                        continue
                    pid = str(row.get("persons_id") or "")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    if args.limit and (applied + skipped + manual + missing) >= args.limit:
                        break
                    cur.execute("SELECT * FROM persons WHERE persons_id=%s", (pid,))
                    current = cur.fetchone()
                    if current is None:
                        missing += 1
                        rows_report.append({"persons_id": pid, "persons_name": row.get("persons_name"),
                                            "status": "missing"})
                        continue
                    person = str(row.get("person") or "").strip().lower()
                    comment = str(row.get("comentario") or "").strip()
                    if person not in {"sí", "si", "yes"}:
                        manual += 1
                        rows_report.append({"persons_id": pid, "persons_name": row.get("persons_name"),
                                            "status": "not_person", "reason": comment})
                        continue
                    if comment and DELICATE.search(comment):
                        manual += 1
                        rows_report.append({"persons_id": pid, "persons_name": row.get("persons_name"),
                                            "status": "manual", "reason": comment})
                        continue
                    changes = {}
                    for key, column in FIELDS.items():
                        value = row.get(key)
                        if value in (None, "", []):
                            continue
                        if _norm(current.get(column)) == _norm(value):
                            continue
                        changes[column] = value
                    if not changes:
                        skipped += 1
                        rows_report.append({"persons_id": pid, "persons_name": row.get("persons_name"),
                                            "status": "unchanged"})
                        continue
                    if args.apply:
                        sets = ", ".join(f"{c}=%s" for c in changes)
                        cur.execute(
                            f"UPDATE persons SET {sets}, persons_review_status='reviewed', "
                            "persons_reviewed_at=NOW(6) WHERE persons_id=%s",
                            (*changes.values(), pid),
                        )
                        old_name = str(current.get("persons_name") or "").strip()
                        new_name = str(changes.get("persons_name") or "").strip()
                        if old_name and new_name and old_name != new_name:
                            cur.execute(
                                "INSERT IGNORE INTO persons_aliases "
                                "(person_id, person_aliases_alias, person_aliases_normalized_alias, "
                                "person_aliases_source) VALUES (%s,%s,%s,'ai')",
                                (pid, old_name, old_name.lower()),
                            )
                        applied += 1
                    else:
                        applied += 1
                    rows_report.append({"persons_id": pid, "persons_name": row.get("persons_name"),
                                        "status": "applied" if args.apply else "would_apply",
                                        "changed": ",".join(changes)})
                if args.limit and (applied + skipped + manual + missing) >= args.limit:
                    break
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["persons_id", "persons_name", "status", "reason", "changed"])
        w.writeheader()
        w.writerows(rows_report)
    print(f"aplicados={applied} sin_cambios={skipped} manual={manual} no_encontrados={missing}")
    print(f"informe: {args.report}")
    if not args.apply:
        print("DRY-RUN: no se ha escrito nada (usa --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
