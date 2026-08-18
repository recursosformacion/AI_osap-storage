#!/usr/bin/env python
"""Incorporar candidatos resueltos de `composer_candidate` al Maestro (osap-storage).

Para cada identidad con `resolved_status` resoluble crea UN Composer agrupado por `name_key`
(no uno por obra/variante), añade sus variantes como aliases + evidence, y asocia todas sus
obras (`works.composer_id`). Idempotente: si ya existe por nombre/clave, lo enlaza.

  resolved_by_prolific / mbid / viaf / qid_plus_evidence / name_dates  -> crear (visible=1 si fuerte)
  matched_existing                                                    -> solo asociar obras
  unknown / review sin resolver                                       -> no crear

Uso:
    python scripts/incorporate_candidates.py --db osap_storage \
        [--db-user osap] [--db-password ...] [--test prod-10000-001] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_ANON = {
    "anon", "anon.", "anonymous", "trad", "trad.", "traditional", "tradicional",
    "traditionell", "attrib.", "attributed", "attrib", "unknown", "author unknown",
    "urheber unbekannt", "urheber unbek.", "na", "n/a", "n.a.", "none", "composer",
    "unattributed",
}
_RESOLVABLE = {"resolved_by_prolific", "resolved_by_mbid", "resolved_by_viaf",
               "resolved_by_qid_plus_evidence", "resolved_by_name_dates", "matched_existing"}
_STRONG = {"resolved_by_mbid", "resolved_by_viaf", "resolved_by_qid_plus_evidence",
           "resolved_by_name_dates"}
_SOURCE = "identity-resolver"


def composer_key(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    low = text.lower().replace("'", "").replace("\u2019", "")
    if low in _ANON or low.startswith("urheber unbekannt"):
        return "anonymous"
    text = re.sub(r"\s+\d{3,4}\s*$", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    tokens = re.findall(r"[a-z\u00e0-\u00ff]+", low)
    if not tokens:
        return ""
    if len(tokens) > 1 and tokens[-2] == "o":
        surname = "o" + tokens[-1]
        given = tokens[:-2]
    else:
        surname = tokens[-1]
        given = tokens[:-1]
    firsts = "".join(t[0] for t in given)
    return f"{firsts} {surname}".strip()


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", default="prod-10000-001")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-host", default="127.0.0.1")
    parser.add_argument("--db-user", default="osap2027")
    parser.add_argument("--db-password", default="2027osapdb")
    parser.add_argument("--db-name", default="osap-storage")
    args = parser.parse_args()

    db = {
        "host": args.db_host, "user": args.db_user, "password": args.db_password,
        "database": args.db_name, "charset": "utf8mb4", "cursorclass": pymysql.cursors.DictCursor,
    }
    conn = pymysql.connect(**db)
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(_RESOLVABLE))
            cur.execute(
                f"SELECT attribution, name_key, cleaned_name, work_count, label, resolved_status "
                f"FROM composer_candidate WHERE resolved_status IN ({placeholders}) "
                f"ORDER BY work_count DESC",
                list(_RESOLVABLE),
            )
            cand_rows = cur.fetchall()
            # mapear name_key -> obras (work_ids) desde composer_identity_resolution
            cur.execute(
                "SELECT work_id, attribution FROM composer_identity_resolution WHERE test_id=%s",
                (args.test,),
            )
            works_by_key: dict[str, list[int]] = defaultdict(list)
            for r in cur.fetchall():
                works_by_key[composer_key(r["attribution"])].append(int(r["work_id"]))

        # agrupar por identidad
        groups: dict[str, dict] = {}
        for r in cand_rows:
            key = r["name_key"]
            g = groups.setdefault(key, {"rows": [], "works": 0, "status": r["resolved_status"]})
            g["rows"].append(r)
            g["works"] += int(r["work_count"])

        def best_name(rows):
            return max(rows, key=lambda x: int(x["work_count"]))

        print(f"=== INCORPORAR CANDIDATOS ({'DRY-RUN' if args.dry_run else 'EJECUTANDO'}) ===")
        print(f"  identidades resueltas: {len(groups)} | obras a asociar: {sum(g['works'] for g in groups.values()):,}")
        by_status = defaultdict(int)
        for g in groups.values():
            by_status[g["status"]] += 1
        for s, n in by_status.items():
            print(f"  {s:26}: {n}")

        if args.dry_run:
            print("\n  muestra:")
            for i, (_key, g) in enumerate(sorted(groups.items(), key=lambda kv: kv[1]["works"], reverse=True)):
                if i >= 10:
                    break
                b = best_name(g["rows"])
                nm = (b["cleaned_name"] or b["attribution"])[:45]
                print(f"     {g['works']:>5}  {g['status']:22}  {nm} ({len(g['rows'])} variantes)")
            return 0

        # --- ejecutar ---
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM composers")
            existing = {r["name"].lower(): r["id"] for r in cur.fetchall()}
            created = reused = 0
            works_associated = 0
            pairs: list[tuple] = []
            for key, g in groups.items():
                b = best_name(g["rows"])
                name = b["cleaned_name"] or b["attribution"] or key
                visible = 1 if g["status"] in _STRONG else (1 if g["status"] == "resolved_by_prolific" else 0)
                cid = existing.get(name.lower())
                if cid is None:
                    cid = str(uuid.uuid4())
                    cur.execute(
                        "INSERT INTO composers (id, name, visible, status, review_status, source_system) "
                        "VALUES (%s,%s,%s,'active','not_reviewed',%s)",
                        (cid, name, visible, _SOURCE),
                    )
                    existing[name.lower()] = cid
                    created += 1
                    cur.execute(
                        "INSERT INTO composer_evidence (composer_id, rule, decision, reason, "
                        "anchor_type, anchor_value, channels, identifiers_used, matcher_version) "
                        "VALUES (%s,'creation','auto',%s,'none','none','[]','[]','identity-resolver')",
                        (cid, f"{g['status']}: {g['works']} obras")[:64],
                    )
                else:
                    reused += 1
                # aliases: todas las variantes menos el nombre canónico
                for r in g["rows"]:
                    alias = r["attribution"]
                    if alias and alias != name:
                        cur.execute(
                            "INSERT IGNORE INTO composer_aliases (composer_id, alias, normalized_alias) "
                            "VALUES (%s,%s,%s)", (cid, alias, composer_key(alias)),
                        )
                for wid in works_by_key.get(key, []):
                    pairs.append((cid, wid))
                    works_associated += 1
            if pairs:
                cur.executemany("UPDATE works SET composer_id=%s WHERE id=%s", pairs)
            conn.commit()
        print(f"\n  creados: {created} | reutilizados: {reused} | obras asociadas: {works_associated:,}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
