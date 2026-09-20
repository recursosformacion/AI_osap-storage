"""Diagnóstico read-only de la persona Haydn `f1f53fb0…` (no modifica nada)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

PID = "f1f53fb0-34d0-4402-8a4c-a5b640af3886"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        print("== 1. persons ==")
        cur.execute("SELECT * FROM persons WHERE persons_id=%s", (PID,))
        for k, v in (cur.fetchone() or {}).items():
            print(f"   {k}: {v}")

        print("\n== 2/3. alias (clasificación) ==")
        cur.execute("SELECT id, person_aliases_alias, person_aliases_normalized_alias, "
                    "person_aliases_source FROM persons_aliases WHERE person_id=%s ORDER BY id", (PID,))
        for r in cur.fetchall():
            n = r["person_aliases_normalized_alias"] or ""
            who = "Michael" if "michael" in n else (
                "Joseph" if ("joseph" in n or "ioseph" in n or "josef" in n
                             or n in ("j haydn", "haydn")) else "neutral"
            )
            print(f"   [{who:7s}] {r['id']:>6} {r['person_aliases_alias']!r} ({n}) src={r['person_aliases_source']}")

        print("\n== 4. identidad externa ==")
        cur.execute("SELECT identity_type, identity_value, identity_source, identity_is_anchor, "
                    "identity_strength FROM persons_identity WHERE persons_id=%s", (PID,))
        rows = cur.fetchall()
        for r in rows:
            print("   ", r)
        if not rows:
            print("    (sin filas en persons_identity)")

        print("\n== 5. obras/roles que apuntan a esa persona ==")
        cur.execute("SELECT works_person_roles_role_id role, COUNT(DISTINCT works_person_roles_work_id) obras "
                    "FROM works_person_roles WHERE works_person_roles_person_id=%s GROUP BY 1", (PID,))
        for r in cur.fetchall():
            print("   ", r)
        cur.execute("SELECT w.id, w.works_title FROM works w JOIN works_person_roles r "
                    "ON r.works_person_roles_work_id=w.id "
                    "WHERE r.works_person_roles_person_id=%s AND r.works_person_roles_role_id=1 LIMIT 8", (PID,))
        for r in cur.fetchall():
            print("    obra:", r)

        print("\n== 6. ¿existe ya Michael Haydn? ==")
        cur.execute("SELECT persons_id, persons_name FROM persons WHERE persons_name LIKE '%%ichael%%aydn%%'")
        for r in cur.fetchall():
            print("   ", r)

        print("\n== 7. ¿existe ya Joseph Haydn? ==")
        cur.execute("SELECT persons_id, persons_name FROM persons WHERE persons_name LIKE '%%oseph%%aydn%%' "
                    "OR persons_name LIKE '%%Ioseph%%aydn%%' OR persons_name='Haydn, Joseph'")
        for r in cur.fetchall():
            print("   ", r)
        cur.execute("SELECT a.person_id, a.person_aliases_alias, p.persons_name FROM persons_aliases a "
                    "JOIN persons p ON p.persons_id=a.person_id "
                    "WHERE a.person_aliases_normalized_alias IN ('j haydn','joseph haydn','iosephus haydn') "
                    "AND a.person_id<>%s LIMIT 10", (PID,))
        for r in cur.fetchall():
            print("    alias Joseph en otra persona:", r)
        cur.execute("SELECT rism_person_id, rism_name, rism_gnd, rism_viaf FROM rism_persons "
                    "WHERE rism_name LIKE '%%Haydn%%'")
        for r in cur.fetchall():
            print("    RISM:", r)
    conn.close()


if __name__ == "__main__":
    main()
