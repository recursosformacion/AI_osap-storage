#!/usr/bin/env python
"""Estadísticas del catálogo tras la pasada de identidad (siguiente objetivo).

Reporte SOLO LECTURA (no modifica obras) sobre el estado tras materializar la
resolución en el Maestro. Sirve para priorizar la siguiente fase del catálogo:

  * Cobertura de compositor (obras con/sin Composer, anónimas vs con nombre).
  * Distribución de la resolución por estado (matched/resolved/ambiguous/unknown).
  * Forma del catálogo de compositores (visible/hidden, origen, obras por compositor).
  * Gaps de datos de las obras (título/género/año/instrumentación/idioma).
  * Candidatos a ampliar: compositores con nombre aún sin Composer, priorizados
    por número de obras (long-tail → qué vale la pena resolver primero).

Uso:
    python scripts/catalog_statistics.py --db osap_storage \
        [--db-user osap] [--db-password ...] [--test prod-10000-001]
"""

from __future__ import annotations

import argparse
import sys

import pymysql


def _coerce(v):
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else v
    if isinstance(v, str) and v.lstrip("-").isdigit():
        return int(v)
    return v


def _q(cur, sql: str, *params) -> list[dict]:
    cur.execute(sql, params)
    return [{k: _coerce(v) for k, v in r.items()} for r in cur.fetchall()]


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", default="prod-10000-001")
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
            cov = _q(cur, """
                SELECT COUNT(*) AS total,
                       SUM(composer_id IS NOT NULL) AS con_composer,
                       SUM(composer_id IS NULL) AS sin_composer
                FROM works
            """)[0]
            res = _q(cur, """
                SELECT status, COUNT(*) AS n
                FROM composer_identity_resolution WHERE test_id=%s
                GROUP BY status ORDER BY n DESC
            """, args.test)
            res_total = sum(r["n"] for r in res)
            cat = _q(cur, """
                SELECT COUNT(*) AS total,
                       SUM(visible=1) AS visibles,
                       SUM(visible=0) AS hidden
                FROM composers
            """)[0]
            origen = _q(
                cur,
                "SELECT source_system, COUNT(*) AS n FROM composers "
                "GROUP BY source_system ORDER BY n DESC",
            )
            top = _q(cur, """
                SELECT c.name, c.visible, COUNT(w.id) AS obras
                FROM composers c LEFT JOIN works w ON w.composer_id=c.id
                GROUP BY c.id ORDER BY obras DESC LIMIT 12
            """)
            gaps = _q(cur, """
                SELECT SUM(title IS NULL OR TRIM(title)='') AS sin_titulo,
                       SUM(genre IS NULL OR TRIM(genre)='') AS sin_genero,
                       SUM(year IS NULL) AS sin_anio,
                       SUM(instrumentation IS NULL OR TRIM(instrumentation)='') AS sin_instrumentacion,
                       SUM(language IS NULL OR TRIM(language)='') AS sin_idioma
                FROM works
            """)[0]
            cand = _q(cur, """
                SELECT attribution, COUNT(*) AS obras
                FROM composer_identity_resolution
                WHERE test_id=%s AND status='unknown'
                GROUP BY attribution ORDER BY obras DESC LIMIT 20
            """, args.test)
            n_cand_uniq = _q(cur, """
                SELECT COUNT(DISTINCT attribution) AS n
                FROM composer_identity_resolution WHERE test_id=%s AND status='unknown'
            """, args.test)[0]["n"]

        def pct(x: int, t: int) -> str:
            return f"{x:,} ({100*x/t:.1f}%)" if t else "0"

        print(f"=== ESTADÍSTICAS CATÁLOGO ({args.db_name}) ===")
        print("\n[1] COBERTURA DE COMPOSITOR")
        print(f"  total obras        : {cov['total']:,}")
        print(f"  con Composer       : {pct(cov['con_composer'], cov['total'])}")
        print(f"  sin Composer       : {pct(cov['sin_composer'], cov['total'])}")

        print(f"\n[2] RESOLUCIÓN DE IDENTIDAD (obras con compositor, {res_total})")
        for r in res:
            print(f"  {r['status']:26}: {pct(r['n'], res_total)}")

        print("\n[3] CATÁLOGO DE COMPOSITORES")
        print(f"  total      : {cat['total']:,}")
        print(f"  visibles   : {pct(cat['visibles'], cat['total'])}")
        print(f"  hidden     : {pct(cat['hidden'], cat['total'])}")
        print("  por origen:")
        for r in origen:
            print(f"     {r['source_system']:20}: {r['n']:,}")
        print("  top compositores por nº de obras:")
        for r in top:
            vis = "visible" if r["visible"] else "hidden "
            print(f"     {r['name'][:40]:40} {vis}  {r['obras']} obras")

        print("\n[4] GAPS DE DATOS DE LAS OBRAS")
        labels = [("sin título", "sin_titulo"), ("sin género", "sin_genero"),
                  ("sin año", "sin_anio"), ("sin instrumentación", "sin_instrumentacion"),
                  ("sin idioma", "sin_idioma")]
        for label, key in labels:
            print(f"  {label:20}: {gaps[key]:,}")

        print("\n[5] CANDIDATOS A AMPLIAR (compositores con nombre, aún sin Composer)")
        print(f"  {n_cand_uniq:,} compositores distintos · {res_total - cov['con_composer']} obras sin asociar")
        print("  top por nº de obras (prioridad):")
        for r in cand:
            print(f"     {r['obras']:>4}  {r['attribution'][:60]}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
