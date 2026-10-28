"""Enlaza los creadores extraidos de MXL con representation_persons.

Lee representation_metadata.raw, extrae compose/letrista/arreglista/transcriptor y crea filas
en representation_persons. Si el nombre coincide de forma unica con una persona activa, enlaza
su persons_id; si no, conserva el nombre con person_id NULL. No modifica la obra.

Uso:
    .venv\\Scripts\\python.exe scripts/populate_mxl_representation_persons.py --limit 100
    .venv\\Scripts\\python.exe scripts/populate_mxl_representation_persons.py --limit 0 --apply
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
ROLE = {"composer": 1, "lyricist": 2, "poet": 2, "text": 2, "arranger": 3, "transcriber": 5}


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
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    conn = _db()
    inserted = linked = skipped = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT persons_id, persons_name FROM persons "
                "WHERE persons_status != 'merged' AND persons_type = 'person'"
            )
            people: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for p in cur.fetchall():
                people[_norm(p["persons_name"])].append(p)

            sql = "SELECT representation_id, raw FROM representation_metadata ORDER BY representation_id"
            params: list[Any] = []
            if args.limit:
                sql += " LIMIT %s OFFSET %s"
                params = [args.limit, args.offset]
            cur.execute(sql, params)
            for row in cur.fetchall():
                try:
                    raw = json.loads(row["raw"] or "{}")
                except ValueError:
                    skipped += 1
                    continue
                creators = raw.get("creators") or []
                if not creators:
                    creators = [
                        {"type": key, "name": raw.get(key)}
                        for key in ("composer", "lyricist", "arranger")
                        if raw.get(key)
                    ]
                seen = set()
                for creator in creators:
                    name = str(creator.get("name") or "").strip()
                    role = ROLE.get(str(creator.get("type") or "").casefold())
                    if not name or not role or (name, role) in seen or len(name) > 255:
                        continue
                    seen.add((name, role))
                    candidates = people.get(_norm(name), [])
                    person_id = candidates[0]["persons_id"] if len(candidates) == 1 else None
                    if args.apply:
                        cur.execute(
                            "INSERT INTO representation_persons "
                            "(representation_persons_representation_id, representation_persons_person_id, "
                            "representation_persons_role_id, representation_persons_name) "
                            "VALUES (%s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE representation_persons_person_id="
                            "COALESCE(VALUES(representation_persons_person_id), representation_persons_person_id)",
                            (row["representation_id"], person_id, role, name),
                        )
                    inserted += 1
                    if person_id:
                        linked += 1
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    print(f"creadores={inserted} enlazados={linked} omitidos={skipped}")
    print("BD actualizada" if args.apply else "DRY-RUN: usa --apply para escribir")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
