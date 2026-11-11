"""Backfill de la página de obra CPDL en `works.works_source_url`.

CPDL identifica cada obra con un id de página MediaWiki estable
(`works_origin_id`). La URL de la obra es
`https://www.cpdl.org/wiki/index.php?curid=<id>`, que no cambia aunque se
renombren los ficheros. El importador antiguo guardaba el fichero en
`works_resources.url`, pero dejó `works_source_url` vacío.

Uso:
    python scripts/backfill_cpdl_source_url.py            # simulación
    python scripts/backfill_cpdl_source_url.py --apply    # escribe
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

PAGE_URL = "https://www.cpdl.org/wiki/index.php?curid="
FILTER = (
    "works_origin = 'CPDL' "
    "AND works_origin_id REGEXP '^[0-9]+$' "
    "AND (works_source_url IS NULL OR TRIM(works_source_url) = '')"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rellena works_source_url con la página CPDL estable (?curid=)."
    )
    parser.add_argument("--apply", action="store_true", help="Escribe los cambios.")
    args = parser.parse_args()

    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["name"],
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM works WHERE {FILTER}")
            pending = int(cur.fetchone()[0])
            print(f"CPDL sin URL de página: {pending}")
            if not args.apply:
                print("Simulación; no se ha escrito nada. Usa --apply para ejecutar.")
                return
            cur.execute(
                f"UPDATE works SET works_source_url = CONCAT(%s, works_origin_id) "
                f"WHERE {FILTER}",
                (PAGE_URL,),
            )
            updated = cur.rowcount
        conn.commit()
        print(f"Actualizadas {updated} obras CPDL.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
