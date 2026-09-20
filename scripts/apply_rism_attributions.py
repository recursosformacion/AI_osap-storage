"""Escritura reversible del lote RISM `resolved` aceptado (historial de atribución).

Decisiones del revisor (2026-09-19): 44 `accept`, 2 `review`, 6 `reject`.
NO toca `persons`. `new_composer_id` debe ser una persona **existente** (mapeo por nombre único
RISM ↔ nuestra `persons`); si no mapea, la obra queda fuera (revisión).

    .venv\\Scripts\\python.exe scripts/apply_rism_attributions.py            # dry-run
    .venv\\Scripts\\python.exe scripts/apply_rism_attributions.py --apply
    .venv\\Scripts\\python.exe scripts/apply_rism_attributions.py --revert
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402
from scripts.measure_rism_person_links import link_rows  # noqa: E402

REVIEW = {"lord hear my prayer", "praise the lord my soul"}
REJECT = {"air savoyard", "christmas medley", "cupido", "les buffons", "oh danny boy", "ostend"}


def _matchkey(name: str | None) -> str:
    return " ".join(sorted(norm(name).split()))


def _conn():
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    return pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           autocommit=True, cursorclass=pymysql.cursors.DictCursor)


def _plan(conn, csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as fh:
        proposals = [r for r in csv.DictReader(fh) if r["state"] == "resolved"]

    our_by_key: dict[str, set[str]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute("SELECT persons_id, persons_name FROM persons")
        for row in cur.fetchall():
            our_by_key[_matchkey(row["persons_name"])].add(row["persons_id"])
        cur.execute("SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases")
        for row in cur.fetchall():
            if row["a"]:
                our_by_key[_matchkey(row["a"])].add(row["person_id"])

    rism_person_keys: dict[str, set[str]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute("SELECT rism_person_id, rism_person_names_matchkey k FROM rism_person_names")
        for row in cur.fetchall():
            if row["k"]:
                rism_person_keys[row["rism_person_id"]].add(row["k"])
        cur.execute("SELECT rism_person_id, COALESCE(rism_canonical_id, rism_person_id) canon "
                    "FROM rism_persons")
        canon = {r["rism_person_id"]: r["canon"] for r in cur.fetchall()}

    # persona nuestra para cada rism_person propuesto
    person_map: dict[str, str] = {}
    for rism_id in {p["rism_person_id"] for p in proposals}:
        candidates: set[str] = set()
        for pid, canon_id in canon.items():
            if canon_id == canon.get(rism_id, rism_id):
                for key in rism_person_keys.get(pid, set()):
                    candidates |= our_by_key.get(key, set())
        if len(candidates) == 1:
            person_map[rism_id] = next(iter(candidates))

    plan: list[dict] = []
    with conn.cursor() as cur:
        for p in proposals:
            key = p["title_key"]
            decision = "review" if key in REVIEW else "reject" if key in REJECT else "accept"
            our_person = person_map.get(p["rism_person_id"])
            cur.execute("SELECT works_person_roles_person_id pid FROM works_person_roles "
                        "WHERE works_person_roles_work_id=%s AND works_person_roles_role_id=1",
                        (int(p["work_id"]),))
            existing = cur.fetchall()
            previous = existing[0]["pid"] if existing else None
            ready = decision == "accept" and our_person is not None and previous is None
            plan.append({
                "work_id": int(p["work_id"]), "title_key": key, "decision": decision,
                "rism_person_id": p["rism_person_id"], "rism_name": p["composer_name"],
                "our_person_id": our_person, "previous_composer_id": previous,
                "ready": ready,
            })
    return plan


def run(csv_path: Path, apply: bool, revert: bool, decisions_path: Path,
        batch2: bool = False, exclude_rism: set[str] | None = None) -> None:
    conn = _conn()
    if revert:
        with conn.cursor() as cur:
            cur.execute("SELECT id, work_id, new_composer_id FROM work_attribution_history "
                        "WHERE operation='assign' AND new_composer_id IS NOT NULL "
                        "AND work_id NOT IN (SELECT work_id FROM work_attribution_history "
                        "  WHERE operation='revert')")
            entries = cur.fetchall()
            for e in entries:
                cur.execute("DELETE FROM works_person_roles WHERE works_person_roles_work_id=%s "
                            "AND works_person_roles_person_id=%s AND works_person_roles_role_id=1",
                            (e["work_id"], e["new_composer_id"]))
                cur.execute(
                    "INSERT INTO work_attribution_history (work_id, previous_composer_id, "
                    "new_composer_id, source, operation, confidence) "
                    "VALUES (%s, %s, NULL, 'rism', 'revert', 'revert')",
                    (e["work_id"], e["new_composer_id"]))
        conn.close()
        print(f"revertidas {len(entries)} obras")
        return

    if batch2:
        exclude_rism = exclude_rism or set()
        plan = []
        with conn.cursor() as cur:
            for row in link_rows(conn, decisions_path):
                if row["category"] != "enlazada_viaf" or not row["our_person_id"]:
                    continue
                if row["rism_person_id"] in exclude_rism:
                    continue
                cur.execute(
                    "SELECT works_person_roles_person_id pid FROM works_person_roles "
                    "WHERE works_person_roles_work_id=%s AND works_person_roles_role_id=1",
                    (row["work_id"],))
                existing = cur.fetchall()
                previous = existing[0]["pid"] if existing else None
                plan.append({
                    "work_id": row["work_id"], "title_key": row["title_key"],
                    "decision": "accept", "rism_person_id": row["rism_person_id"],
                    "rism_name": row["rism_name"], "our_person_id": row["our_person_id"],
                    "previous_composer_id": previous,
                    "ready": previous is None and row["our_person_id"] is not None,
                })
        print(f"BATCH2 (solo enlazada_viaf) — obras={len(plan)} "
              f"| excluidas={sorted(exclude_rism)}")
    else:
        plan = _plan(conn, csv_path)
        with open(decisions_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(plan[0].keys()) if plan else ["work_id"])
            writer.writeheader()
            writer.writerows(plan)
        print("decisiones:", decisions_path)

    counts = defaultdict(int)
    for row in plan:
        counts[f"decision_{row['decision']}"] += 1
        counts["ready" if row["ready"] else "no_ready"] += 1
        if row["decision"] == "accept" and row["our_person_id"] is None:
            counts["accept_sin_persona_nuestra"] += 1

    print("plan:", dict(counts))
    samples = [r for r in plan if r["ready"]][:5]
    for s in samples:
        print("  ", s)

    if apply:
        with conn.cursor() as cur:
            for row in plan:
                if not row["ready"]:
                    continue
                cur.execute(
                    "INSERT IGNORE INTO works_person_roles "
                    "(works_person_roles_work_id, works_person_roles_person_id, "
                    " works_person_roles_role_id, works_person_roles_order) VALUES (%s,%s,1,0)",
                    (row["work_id"], row["our_person_id"]))
                cur.execute(
                    "INSERT INTO work_attribution_history (work_id, previous_composer_id, "
                    "new_composer_id, source, rism_person_id, confidence, evidence_json, operation) "
                    "VALUES (%s,%s,%s,'rism',%s,%s,%s,'assign')",
                    (row["work_id"], row["previous_composer_id"], row["our_person_id"],
                     row["rism_person_id"], "Verified",
                     json.dumps({"title_key": row["title_key"], "rism_name": row["rism_name"]},
                                ensure_ascii=False)))
        print("APLICADO")
    conn.close()


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\rism_composer_proposals.csv"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--batch2", action="store_true")
    ap.add_argument("--exclude-rism", default="")
    ap.add_argument("--decisions", type=Path, default=Path(r"G:\rism\rism_decisions.csv"))
    args = ap.parse_args()
    exclude = {x.strip() for x in args.exclude_rism.split(",") if x.strip()}
    run(args.csv, args.apply, args.revert, args.decisions, args.batch2, exclude)


if __name__ == "__main__":
    main()
