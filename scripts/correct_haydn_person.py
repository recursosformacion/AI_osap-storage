"""Corrección de identidad de la persona Haydn `f1f53fb0…` (Joseph con nombre de Michael).

Dry-run por defecto. No toca obras ni atribuciones. Auditable y reversible.

    .venv\\Scripts\\python.exe scripts/correct_haydn_person.py            # dry-run
    .venv\\Scripts\\python.exe scripts/correct_haydn_person.py --apply
    .venv\\Scripts\\python.exe scripts/correct_haydn_person.py --revert
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

PID = "f1f53fb0-34d0-4402-8a4c-a5b640af3886"
MICHAEL = "96714c71-797a-4fcc-a588-b6699bd7241f"
ALIASES = [10211, 53398, 2460]
REASON = "contaminación del import (from/Arranged from) sobre la persona de Joseph Haydn"
NEW = {
    "persons_name": "Joseph Haydn",
    "persons_givenname": "Joseph",
    "persons_familyname": "Haydn",
    "persons_sortname": "Haydn, Joseph",
    "persons_birth_year": 1732,
    "persons_death_year": 1809,
    "persons_review_status": "reviewed",
    "persons_review_reason": REASON,
}
DDL = """
CREATE TABLE IF NOT EXISTS `persons_correction_history` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `persons_id` char(36) NOT NULL,
  `operation` varchar(16) NOT NULL DEFAULT 'correct',
  `reason` varchar(255) DEFAULT NULL,
  `before_json` text DEFAULT NULL,
  `after_json` text DEFAULT NULL,
  `aliases_moved_json` text DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_pch_person` (`persons_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def _conn():
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    return pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           autocommit=True, cursorclass=pymysql.cursors.DictCursor)


def _snapshot(cur) -> dict:
    cur.execute("SELECT persons_name, persons_givenname, persons_familyname, persons_sortname, "
                "persons_birth_year, persons_death_year, persons_review_status, "
                "persons_review_reason FROM persons WHERE persons_id=%s", (PID,))
    before = cur.fetchone()
    cur.execute("SELECT works_person_roles_role_id role, COUNT(DISTINCT works_person_roles_work_id) n "
                "FROM works_person_roles WHERE works_person_roles_person_id=%s GROUP BY 1", (PID,))
    roles = {r["role"]: r["n"] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) n FROM persons_identity WHERE persons_id=%s", (PID,))
    identities = cur.fetchone()["n"]
    cur.execute("SELECT id, person_id FROM persons_aliases WHERE id IN (10211, 53398, 2460)")
    return {"before": before, "roles": roles, "identities": identities,
            "aliases": cur.fetchall()}


def run(apply: bool, revert: bool) -> None:
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute(DDL)
        if revert:
            cur.execute("SELECT id, before_json, aliases_moved_json FROM persons_correction_history "
                        "WHERE persons_id=%s AND operation='correct' ORDER BY id DESC LIMIT 1", (PID,))
            row = cur.fetchone()
            if not row:
                print("nada que revertir")
                conn.close()
                return
            before = json.loads(row["before_json"])
            cur.execute(
                "UPDATE persons SET persons_name=%s, persons_givenname=%s, persons_familyname=%s, "
                "persons_sortname=%s, persons_birth_year=%s, persons_death_year=%s, "
                "persons_review_status=%s, persons_review_reason=%s WHERE persons_id=%s",
                (before["persons_name"], before["persons_givenname"], before["persons_familyname"],
                 before["persons_sortname"], before["persons_birth_year"], before["persons_death_year"],
                 before["persons_review_status"], before["persons_review_reason"], PID))
            cur.execute("UPDATE persons_aliases SET person_id=%s WHERE id IN (10211, 53398, 2460)", (PID,))
            cur.execute("INSERT INTO persons_correction_history (persons_id, operation, reason) "
                        "VALUES (%s, 'revert', %s)", (PID, REASON))
            print("REVERTIDO")
            conn.close()
            return

        snap = _snapshot(cur)
        print("== estado actual ==")
        print("  before:", snap["before"])
        print("  roles:", snap["roles"], "| identidades:", snap["identities"])
        print("  alias a mover:", snap["aliases"])
        print("== plan ==")
        for k, v in NEW.items():
            print(f"  {k}: {snap['before'].get(k)!r} -> {v!r}")
        print(f"  mover alias {ALIASES} a {MICHAEL} ({'Michael Haydn'})")
        ok = (
            {r["id"] for r in snap["aliases"]} == set(ALIASES)
            and all(r["person_id"] == PID for r in snap["aliases"])
        )
        print("== comprobaciones ==")
        print("  alias 3 y en la persona de Joseph:", ok)
        print("  roles que NO se tocan:", snap["roles"])
        print("  identidades que se conservan:", snap["identities"])

        if apply and ok:
            cur.execute(
                "UPDATE persons SET persons_name=%s, persons_givenname=%s, persons_familyname=%s, "
                "persons_sortname=%s, persons_birth_year=%s, persons_death_year=%s, "
                "persons_review_status=%s, persons_review_reason=%s WHERE persons_id=%s",
                (NEW["persons_name"], NEW["persons_givenname"], NEW["persons_familyname"],
                 NEW["persons_sortname"], NEW["persons_birth_year"], NEW["persons_death_year"],
                 NEW["persons_review_status"], NEW["persons_review_reason"], PID))
            cur.execute("UPDATE persons_aliases SET person_id=%s WHERE id IN (10211, 53398, 2460)",
                        (MICHAEL,))
            cur.execute(
                "INSERT INTO persons_correction_history (persons_id, operation, reason, "
                "before_json, after_json, aliases_moved_json) VALUES (%s,'correct',%s,%s,%s,%s)",
                (PID, REASON, json.dumps(snap["before"], default=str, ensure_ascii=False),
                 json.dumps(NEW, default=str, ensure_ascii=False), json.dumps(ALIASES)))
            # verificación post
            cur.execute("SELECT works_person_roles_role_id role, COUNT(DISTINCT works_person_roles_work_id) n "
                        "FROM works_person_roles WHERE works_person_roles_person_id=%s GROUP BY 1", (PID,))
            roles_after = {r["role"]: r["n"] for r in cur.fetchall()}
            cur.execute("SELECT COUNT(*) n FROM persons_identity WHERE persons_id=%s", (PID,))
            ids_after = cur.fetchone()["n"]
            cur.execute("SELECT person_id, COUNT(*) n FROM persons_aliases WHERE id IN (10211,53398,2460) "
                        "GROUP BY 1")
            alias_after = cur.fetchall()
            cur.execute("SELECT COUNT(*) n FROM persons WHERE persons_name='Joseph Haydn'")
            josephs = cur.fetchone()["n"]
            print("== resultado ==")
            print("  roles iguales:", roles_after == snap["roles"], roles_after)
            print("  identidades iguales:", ids_after == snap["identities"], ids_after)
            print("  alias ahora en:", alias_after)
            print("  personas llamadas 'Joseph Haydn':", josephs)
            print("APLICADO")
        else:
            print("DRY-RUN (sin escribir)")
    conn.close()


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    run(args.apply, args.revert)


if __name__ == "__main__":
    main()
