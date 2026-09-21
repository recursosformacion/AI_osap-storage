"""Revierte la limpieza naive de `persons` restaurando el nombre importado.

`clean_persons.py` (v1) rellenó `given/family/sortname` con heurísticas demasiado simples
(years/annotations dentro del nombre). Este script:
1. Localiza las personas tocadas por esa pasada (`persons_updated_at` reciente, `--minutes`).
2. Restaura `persons_name` desde `persons_identity.identity_name` (nombre importado; se
   prefiere el ancla) cuando existe.
3. Deja a NULL los campos derivados (given/family/sort/birth/death) para no conservar datos
   incorrectos.

    .venv\\Scripts\\python.exe scripts/revert_clean_persons.py --minutes 120
    .venv\\Scripts\\python.exe scripts/revert_clean_persons.py --minutes 120 --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=120, help="ventana de personas tocadas")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with open(ROOT / "config.yaml", encoding="utf-8") as handle:
        conf = (yaml.safe_load(handle) or {}).get("db") or {}
    conn = pymysql.connect(
        host=conf.get("host", "127.0.0.1"),
        port=int(conf.get("port", 3306)),
        user=conf.get("user"),
        password=conf.get("password"),
        database=conf.get("name") or conf.get("database"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.persons_id, p.persons_name, i.identity_name "
                "FROM persons p "
                "JOIN persons_identity i ON i.persons_id = p.persons_id "
                "WHERE p.persons_updated_at >= (NOW() - INTERVAL %s MINUTE) "
                "ORDER BY i.identity_is_anchor DESC, i.id",
                (args.minutes,),
            )
            rows = cur.fetchall()
            restored: dict[str, str] = {}
            for row in rows:
                restored.setdefault(str(row["persons_id"]), str(row["identity_name"] or ""))
            print(f"personas tocadas con identidad recuperable: {len(restored)}")
            for pid, name in list(restored.items())[:5]:
                print(f"  {pid[:8]}… -> {name[:60]!r}")
            if not args.apply:
                print("DRY-RUN: usa --apply para restaurar.")
                return 0
            changed = 0
            for pid, name in restored.items():
                if not name:
                    continue
                cur.execute(
                    "UPDATE persons SET persons_name=%s, persons_givenname=NULL, "
                    "persons_familyname=NULL, persons_sortname=NULL, persons_birth_year=NULL, "
                    "persons_death_year=NULL, persons_updated_at=NOW() WHERE persons_id=%s",
                    (name[:1024], pid),
                )
                changed += cur.rowcount
            print(f"restauradas: {changed}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
