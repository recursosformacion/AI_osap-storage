"""2C.1 — Canonicaliza las personas RISM por GND/VIAF compartidos (read-only para el dominio).

Dos personas RISM que comparten GND o VIAF son la misma persona. Calcula una unión (union-find)
determinista y guarda el id canónico en `rism_persons.rism_canonical_id`.

Solo toca el índice externo `rism_persons` (columna añadida si falta). NO toca `persons`.

    .venv\\Scripts\\python.exe scripts/canonicalize_rism_persons.py
    .venv\\Scripts\\python.exe scripts/canonicalize_rism_persons.py --db osap-storage
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402


def canonical_map(rows: list[dict]) -> dict[str, str]:
    """Union-find por GND/VIAF. `rows`: [{rism_person_id, rism_gnd, rism_viaf}]."""
    parent: dict[str, str] = {r["rism_person_id"]: r["rism_person_id"] for r in rows}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # representante determinista (menor id)

    for field in ("rism_gnd", "rism_viaf"):
        by_value: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            if r[field]:
                by_value[r[field]].append(r["rism_person_id"])
        for ids in by_value.values():
            for other in ids[1:]:
                union(ids[0], other)

    return {r["rism_person_id"]: find(r["rism_person_id"]) for r in rows}


def run(db_name: str) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=db_name, charset="utf8mb4",
                           autocommit=True, cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) n FROM information_schema.columns WHERE table_schema=%s "
            "AND table_name='rism_persons' AND column_name='rism_canonical_id'",
            (db_name,),
        )
        if cur.fetchone()["n"] == 0:
            cur.execute(
                "ALTER TABLE rism_persons ADD COLUMN rism_canonical_id varchar(32) NULL AFTER rism_person_id"
            )
            cur.execute(
                "ALTER TABLE rism_persons ADD KEY idx_rism_canonical (rism_canonical_id)"
            )
            print("columna rism_canonical_id añadida")
        cur.execute("SELECT rism_person_id, rism_gnd, rism_viaf FROM rism_persons")
        rows = cur.fetchall()

    mapping = canonical_map(rows)
    merged = sum(1 for pid, canon in mapping.items() if pid != canon)
    updates = [(mapping[r["rism_person_id"]], r["rism_person_id"]) for r in rows]
    with conn.cursor() as cur:
        batch = 2000
        for i in range(0, len(updates), batch):
            cur.executemany(
                "UPDATE rism_persons SET rism_canonical_id=%s WHERE rism_person_id=%s",
                updates[i:i + batch],
            )
    conn.close()
    print(f"[{db_name}] personas={len(rows)} fusionadas_con_canonico={merged}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    args = ap.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
