"""Aplica el compositor de las propuestas MXL cuando ya existe una persona con ese nombre.

No crea personas ni cambia nombres. Solo asocia el rol principal de la obra a una persona
existente y activa cuando el nombre normalizado coincide de forma única. Las obras con un
compositor válido distinto quedan como conflicto.

Uso dev:
    .venv\\Scripts\\python.exe scripts/apply_mxl_metadata.py --dry-run
    .venv\\Scripts\\python.exe scripts/apply_mxl_metadata.py --apply
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "data" / "mxl_metadata" / "proposals_20261027.json"


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _db():
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    if conf.get("host") not in {"127.0.0.1", "localhost"}:
        raise SystemExit("rechazado: host no local")
    return pymysql.connect(
        host=conf["host"], port=conf["port"], user=conf["user"], password=conf["password"],
        database=conf["name"], charset="utf8mb4", cursorclass=DictCursor,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rows = __import__("json").loads(args.file.read_text(encoding="utf-8"))
    conn = _db()
    applied = conflicts = missing_person = already = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT persons_id, persons_name FROM persons "
                "WHERE persons_status != 'merged' AND persons_type = 'person'"
            )
            people: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for person in cur.fetchall():
                people[_norm(person["persons_name"])].append(person)

            work_ids = [int(row["work_id"]) for row in rows if row.get("composer")]
            roles: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for start in range(0, len(work_ids), 1000):
                chunk = work_ids[start : start + 1000]
                placeholders = ",".join(["%s"] * len(chunk))
                cur.execute(
                    "SELECT r.works_person_roles_work_id AS work_id, "
                    "r.works_person_roles_person_id AS person_id, "
                    "p.persons_status, p.persons_type "
                    "FROM works_person_roles r LEFT JOIN persons p "
                    "ON p.persons_id=r.works_person_roles_person_id "
                    f"WHERE r.works_person_roles_role_id=1 AND r.works_person_roles_work_id IN ({placeholders})",
                    chunk,
                )
                for role in cur.fetchall():
                    roles[int(role["work_id"])].append(role)

            for row in rows:
                composer = row.get("composer")
                if not composer:
                    continue
                candidates = people.get(_norm(composer), [])
                if len(candidates) != 1:
                    missing_person += 1
                    continue
                target = candidates[0]["persons_id"]
                work_id = int(row["work_id"])
                current = roles.get(work_id, [])
                if not current:
                    if args.apply:
                        cur.execute(
                            "INSERT INTO works_person_roles "
                            "(works_person_roles_work_id, works_person_roles_person_id, works_person_roles_role_id) "
                            "VALUES (%s, %s, 1)",
                            (work_id, target),
                        )
                    applied += 1
                    continue
                valid = [
                    r for r in current
                    if r.get("persons_status") != "merged" and r.get("persons_type") == "person"
                ]
                if any(r["person_id"] == target for r in valid):
                    already += 1
                elif valid:
                    conflicts += 1
                else:
                    if args.apply:
                        cur.execute(
                            "UPDATE works_person_roles SET works_person_roles_person_id=%s "
                            "WHERE works_person_roles_work_id=%s AND works_person_roles_role_id=1",
                            (target, work_id),
                        )
                    applied += 1
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    print(
        f"filas={len(rows)} aplicadas={applied} ya_estaban={already} "
        f"sin_persona={missing_person} conflictos={conflicts}"
    )
    print("BD actualizada" if args.apply else "DRY-RUN: no se ha escrito nada (usa --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

