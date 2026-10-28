"""Crea personas desde compositores MXL limpios y asocia sus obras.

Solo crea una persona si el nombre limpio no coincide con una persona existente y al menos
una obra no tiene un compositor valido distinto. No pisa conflictos.

Uso dev:
    .venv\\Scripts\\python.exe scripts/create_mxl_composers.py
    .venv\\Scripts\\python.exe scripts/create_mxl_composers.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "mxl_metadata" / "new_composer_candidates.json"


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _clean_name(value: str) -> str:
    text = re.sub(r"^[\s:;\"'`.,\-–—]+", "", value or "")
    text = re.sub(r"[\s:;\"'`.,\-–—]+$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _invalid_name(value: str) -> bool:
    return (
        len(value) < 4
        or len(value) > 80
        or not re.search(r"[A-Za-zÀ-ÿ]", value)
        or bool(
            re.search(
                r"(?i)\b(anon|unknown|trad|folk song|popular dance|transcribed|arranged|collection|untitled)\b",
                value,
            )
        )
    )


def _db():
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    if conf.get("host") not in {"127.0.0.1", "localhost"}:
        raise SystemExit("rechazado: host no local")
    return pymysql.connect(
        host=conf["host"], port=conf["port"], user=conf["user"], password=conf["password"],
        database=conf["name"], charset="utf8mb4", cursorclass=DictCursor,
    )


def _role(cur, work_id: int) -> dict[str, Any] | None:
    cur.execute(
        "SELECT r.works_person_roles_person_id p, p.persons_status s, p.persons_type t "
        "FROM works_person_roles r LEFT JOIN persons p "
        "ON p.persons_id=r.works_person_roles_person_id "
        "WHERE r.works_person_roles_work_id=%s AND r.works_person_roles_role_id=1",
        (work_id,),
    )
    return cur.fetchone()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    candidates = [c for c in candidates if not c.get("match")]
    conn = _db()
    created = associated = already = conflicts = skipped = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT persons_id, persons_name FROM persons "
                "WHERE persons_status != 'merged' AND persons_type = 'person'"
            )
            existing: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for p in cur.fetchall():
                existing[_norm(p["persons_name"])].append(p)

            for candidate in candidates:
                name = _clean_name(str(candidate.get("persons_name") or ""))
                key = _norm(name)
                works = [int(w) for w in candidate.get("work_ids") or []]
                if not name or not works or _invalid_name(name):
                    skipped += 1
                    continue
                targets = existing.get(key, [])
                if len(targets) > 1:
                    skipped += 1
                    continue
                target = targets[0]["persons_id"] if targets else None
                eligible: list[int] = []
                for wid in works:
                    role = _role(cur, wid)
                    if role and role.get("p") == target:
                        already += 1
                        continue
                    if role and role.get("s") != "merged" and role.get("t") == "person":
                        conflicts += 1
                        continue
                    eligible.append(wid)
                if target is None:
                    if not eligible:
                        skipped += 1
                        continue
                    target = str(uuid.uuid4())
                    if args.apply:
                        cur.execute(
                            "INSERT INTO persons (persons_id, persons_name, persons_visible, persons_status, "
                            "persons_review_status, persons_source_system, persons_type) "
                            "VALUES (%s, %s, 1, 'active', 'not_reviewed', 'mxl_metadata', 'person')",
                            (target, name),
                        )
                    created += 1
                for wid in eligible:
                    if args.apply:
                        cur.execute(
                            "INSERT INTO works_person_roles "
                            "(works_person_roles_work_id, works_person_roles_person_id, works_person_roles_role_id) "
                            "VALUES (%s, %s, 1) "
                            "ON DUPLICATE KEY UPDATE works_person_roles_person_id=VALUES(works_person_roles_person_id)",
                            (wid, target),
                        )
                        associated += 1
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    print(
        f"candidatos={len(candidates)} personas_creadas={created} obras_asociadas={associated} "
        f"ya_estaban={already} conflictos={conflicts} omitidos={skipped}"
    )
    print("BD actualizada" if args.apply else "DRY-RUN: no se ha escrito nada (usa --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
