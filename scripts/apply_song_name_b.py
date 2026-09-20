"""Ejecución reversible del subconjunto A de `works_song_name` B (87 casos).

Valida contra la BBDD antes de aplicar (aborta si cambia), guarda el valor previo en
`works_field_history` y permite revert exacto. Solo modifica `works_song_name`.

    .venv\\Scripts\\python.exe scripts/apply_song_name_b.py            # dry-run
    .venv\\Scripts\\python.exe scripts/apply_song_name_b.py --apply
    .venv\\Scripts\\python.exe scripts/apply_song_name_b.py --revert
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402

FIELD = "works_song_name"


def _load(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["classification"] == "A"]


def run(csv_path: Path, apply: bool, revert: bool) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           autocommit=False, cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()

    if revert:
        cur.execute("SELECT batch_id FROM works_field_history WHERE field=%s AND operation='strip' "
                    "ORDER BY id DESC LIMIT 1", (FIELD,))
        row = cur.fetchone()
        if not row:
            print("nada que revertir")
            conn.close()
            return
        batch = row["batch_id"]
        cur.execute("SELECT work_id, old_value FROM works_field_history WHERE batch_id=%s", (batch,))
        entries = cur.fetchall()
        for e in entries:
            cur.execute("UPDATE works SET works_song_name=%s WHERE id=%s", (e["old_value"], e["work_id"]))
        cur.execute("DELETE FROM works_field_history WHERE batch_id=%s", (batch,))
        conn.commit()
        print(f"REVERTIDO batch {batch}: {len(entries)} restauraciones")
        conn.close()
        return

    rows = _load(csv_path)
    mismatches = 0
    for r in rows:
        wid = int(r["work_id"])
        cur.execute("SELECT works_title, works_song_name, "
                    " (SELECT p.persons_name FROM works_person_roles wpr JOIN persons p "
                    "   ON p.persons_id=wpr.works_person_roles_person_id "
                    "  WHERE wpr.works_person_roles_work_id=w.id AND wpr.works_person_roles_role_id=1 "
                    "  LIMIT 1) composer "
                    "FROM works w WHERE id=%s", (wid,))
        w = cur.fetchone()
        if not w or (w["works_song_name"] or "") != "" or w["works_title"] != r["works_title"]:
            mismatches += 1
            continue
        if "sufijo_igual_compositor" in r["evidence"] and (
                not w["composer"] or norm(w["composer"]) != norm(r["candidate_suffix"])):
            mismatches += 1
        if not r["proposed_song_name"]:
            mismatches += 1
    print(f"A={len(rows)} mismatches={mismatches}")
    if mismatches:
        print("ABORTADO: el CSV no coincide con el estado actual.")
        conn.close()
        return
    if not apply:
        conn.close()
        print("DRY-RUN (sin escribir)")
        return

    batch = str(uuid.uuid4())
    changed = 0
    for r in rows:
        wid = int(r["work_id"])
        cur.execute("SELECT works_song_name s FROM works WHERE id=%s", (wid,))
        old = cur.fetchone()["s"]
        cur.execute("INSERT INTO works_field_history (work_id, field, old_value, new_value, "
                    "operation, batch_id) VALUES (%s,%s,%s,%s,'strip',%s)",
                    (wid, FIELD, old, r["proposed_song_name"], batch))
        cur.execute("UPDATE works SET works_song_name=%s WHERE id=%s", (r["proposed_song_name"], wid))
        changed += 1
    conn.commit()
    cur.execute("SELECT COUNT(*) n FROM works_field_history WHERE batch_id=%s", (batch,))
    print(f"APLICADO batch {batch}: {changed} cambios (historial {cur.fetchone()['n']})")
    conn.close()


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\works_song_name_B_dry_run.csv"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    run(args.csv, args.apply, args.revert)


if __name__ == "__main__":
    main()
