#!/usr/bin/env python
"""Prioriza candidatos a Composer por impacto (nº de obras), agrupando por identidad.

Lee `composer_candidate` (producido por candidate_cleanup) y agrupa las atribuciones por
`name_key` (la misma normalización del identity_resolver), sumando las obras. Devuelve el
top N por obras: son los compositores que concentran más obras y por tanto el mayor
rendimiento de la siguiente pasada de identity-resolver.

  Agrupación: "Wolfgang Amadeus Mozart" + "W. A. Mozart" -> 1 identidad, obras sumadas.

Uso:
    python scripts/candidate_priority.py --db osap_storage \
        [--db-user osap] [--db-password ...] [--label real] [--limit 200]
"""

from __future__ import annotations

import argparse
import sys

import pymysql


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="real", choices=("real", "review", "all"))
    parser.add_argument("--limit", type=int, default=200)
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
        where = "" if args.label == "all" else f"WHERE label='{args.label}'"
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT attribution, name_key, cleaned_name, work_count, label "
                f"FROM composer_candidate {where} ORDER BY work_count DESC"
            )
            rows = cur.fetchall()

        groups: dict[str, dict] = {}
        for r in rows:
            key = r["name_key"]
            g = groups.setdefault(key, {"works": 0, "n": 0, "name": "", "label": r["label"]})
            g["works"] += int(r["work_count"])
            g["n"] += 1
            if not g["name"]:
                g["name"] = r["cleaned_name"] or r["attribution"]

        ranked = sorted(groups.values(), key=lambda g: g["works"], reverse=True)
        print(f"=== PRIORIDAD CANDIDATOS (label={args.label}) ===")
        print(f"  identidades: {len(ranked):,} | obras totales: {sum(g['works'] for g in ranked):,}")
        print(f"  top {min(args.limit, len(ranked))} por impacto:\n")
        print(f"  {'obras':>6}  {'variantes':>5}  compositor")
        for g in ranked[: args.limit]:
            print(f"  {g['works']:>6}  {g['n']:>5}  {g['name'][:60]}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
