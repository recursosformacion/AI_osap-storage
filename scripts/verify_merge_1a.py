"""Verificador read-only del Lote 1A (estado de merges, snapshots y referencias)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

ORIGINS = {
    "70c8c36c-86ee-4ecc-baa3-b9e489502a60": "From Beethoven",
    "89d0174e-4ef7-4692-aa5b-431fabc4c514": "Arranged from Beethoven (1770-1827)",
    "c63a6a9d-a7ff-4db9-8065-5de004db144d": "Arranged from Beethoven",
    "d9977651-501c-4cda-831b-c0d158ec4ad4": "from Beethoven (1770-1827)",
    "46efddc8-6acd-4cf7-9605-5ad2faea8558": "Arranged from Haydn",
    "dbbf4b8f-93be-467d-bc93-4cf92990e2ba": "Arranged from Schubert",
    "b63cde50-a57f-4ea3-a9ee-aab9ba9ac9a6": "Arr Alexander Maltas",
}
TARGETS = {
    "e8994f5a-f1de-4676-bb00-7c2c8af2b2df": "Beethoven",
    "f1f53fb0-34d0-4402-8a4c-a5b640af3886": "Joseph Haydn",
    "2adf9877-4120-58ac-a003-7d728ef6cbf1": "Schubert",
    "8d071f03-5680-4dc7-893d-498a984915c3": "Maltas",
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM persons_merge_history WHERE merged_by='rism-lote1a'")
        print("history lote1A:", cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) n FROM persons_merge_snapshot")
        print("snapshots:", cur.fetchone()["n"])
        print("-- orígenes --")
        for pid, name in ORIGINS.items():
            cur.execute("SELECT persons_merged_into FROM persons WHERE persons_id=%s", (pid,))
            merged = (cur.fetchone() or {}).get("persons_merged_into")
            cur.execute("SELECT COUNT(*) n FROM works_person_roles WHERE works_person_roles_person_id=%s", (pid,))
            wpr = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) n FROM persons_aliases WHERE person_id=%s", (pid,))
            al = cur.fetchone()["n"]
            print(f"  {name:36s} merged_into={'sí' if merged else 'no':3s} wpr={wpr} alias={al}")
        print("-- destinos (roles por rol) --")
        for pid, name in TARGETS.items():
            cur.execute("SELECT works_person_roles_role_id r, COUNT(*) n FROM works_person_roles "
                        "WHERE works_person_roles_person_id=%s GROUP BY 1 ORDER BY 1", (pid,))
            print(f"  {name:16s}", {x["r"]: x["n"] for x in cur.fetchall()})
    conn.close()


if __name__ == "__main__":
    main()
