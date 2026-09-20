"""Marca en `works` las obras confirmadas como anónimas/tradicionales (no van a persons).

Las obras sin compositor (sin rol 1 en `works_person_roles`) cuyo título o nota de
atribución declara anonimato/tradición se marcan con `works_attr_type`
(TRADICIONAL / ANONIMA / POPULAR / DESCONOCIDO). Así quedan "dadas por hechas" en la obra,
sin crear personas falsas, y el índice puede anunciarlas como "Anónimo"/"Tradicional".

Idempotente: solo toca filas con `works_attr_type IS NULL` y sin rol 1.

    .venv\\Scripts\\python.exe scripts/mark_anonymous_attr.py --dry-run
    .venv\\Scripts\\python.exe scripts/mark_anonymous_attr.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

_ANON_PATTERN = "anon|anonym|unknown|unbekannt|desconocid|sin autor|vvaa|varios|various|autor desconocido"
_TRAD_PATTERN = "tradicional|traditional|popular|folk|volkslied|trad\\."


def _db_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    db = cfg.get("db") or cfg.get("database") or {}
    return {
        "host": db.get("host", "127.0.0.1"),
        "port": int(db.get("port", 3306)),
        "user": db.get("user"),
        "password": db.get("password"),
        "database": db.get("name") or db.get("database"),
    }


_CLASSIFY = f"""
    CASE
        WHEN w.works_title REGEXP %(trad)s OR w.works_attribution_note REGEXP %(trad)s
            THEN 'TRADICIONAL'
        WHEN w.works_title REGEXP %(anon)s OR w.works_attribution_note REGEXP %(anon)s
            THEN 'ANONIMA'
        ELSE 'DESCONOCIDO'
    END
"""

_FILTER = f"""
    w.works_attr_type IS NULL
    AND NOT EXISTS (
        SELECT 1 FROM works_person_roles r
        WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1
    )
    AND (
        w.works_title REGEXP %(anon)s OR w.works_attribution_note REGEXP %(anon)s
        OR w.works_title REGEXP %(trad)s OR w.works_attribution_note REGEXP %(trad)s
    )
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="escribe (por defecto dry-run)")
    args = parser.parse_args()

    params = {"anon": _ANON_PATTERN, "trad": _TRAD_PATTERN}
    conn = pymysql.connect(**_db_config(), charset="utf8mb4", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM works w WHERE {_FILTER}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"SELECT {_CLASSIFY} AS tipo, COUNT(*) AS n FROM works w WHERE {_FILTER} "
                "GROUP BY 1 ORDER BY n DESC",
                params,
            )
            por_tipo = cur.fetchall()
            print(f"candidatas (sin rol 1 y sin marca): {total}")
            for tipo, n in por_tipo:
                print(f"  {tipo}: {n}")
            if not args.apply:
                print("DRY-RUN: usa --apply para escribir works_attr_type.")
                return 0
            cur.execute(
                f"UPDATE works w SET w.works_attr_type = {_CLASSIFY} WHERE {_FILTER}",
                params,
            )
            print(f"aplicado: {cur.rowcount} obras marcadas")
            cur.execute(
                "SELECT works_attr_type, COUNT(*) FROM works GROUP BY 1 ORDER BY 2 DESC LIMIT 8"
            )
            for tipo, n in cur.fetchall():
                print(f"  ahora {tipo}: {n}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
