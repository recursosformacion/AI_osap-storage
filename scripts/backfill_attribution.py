#!/usr/bin/env python
"""Backfill de atribución de obras: mover atribuciones no-persona a attribution_type/note.

Toma las obras cuyo `composer` es una atribución no-persona (anónima, tradicional, popular,
atribuida) y las mueve a los campos nuevos:
  attribution_type  -> ANONIMA / TRADICIONAL / POPULAR / ATRIBUIDA (según patrón)
  attribution_note  -> el texto original (ej. "Traditional English")
y limpia composer / composer_id (para no tratarlas como persona).

Idempotente: solo procesa obras con composer no vacío que matchee los patrones.

Uso:
    python scripts/backfill_attribution.py --db osap_storage \
        [--db-user osap] [--db-password ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys

import pymysql

_ATTR_PATTERNS = [
    (re.compile(r"\b(anon|anonymous|anonimo|anónimo)\b", re.I), "ANONIMA"),
    (re.compile(r"\b(unknown|unbekannt|desconocido|composer unknown|autor desconocido)\b", re.I), "DESCONOCIDO"),
    (re.compile(r"\b(traditional|trad|tradicional|traditionell|traditionnel|folk)\b", re.I), "TRADICIONAL"),
    (re.compile(r"\b(popular|popular)\b", re.I), "POPULAR"),
    (re.compile(r"\b(attrib|attributed|atribuida|atribuido)\b", re.I), "ATRIBUIDA"),
]


def _classify(name: str) -> tuple[str | None, str]:
    """Devuelve (attribution_type, note). Si no matchea, (None, name)."""
    for pat, tipo in _ATTR_PATTERNS:
        if pat.search(name or ""):
            return tipo, (name or "").strip()
    return None, (name or "").strip()


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
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
            cur.execute(
                "SELECT id, composer, composer_id, attribution_type FROM works "
                "WHERE composer IS NOT NULL AND TRIM(composer)<>''"
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT id, attribution_type, attribution_note FROM works "
                "WHERE attribution_type IS NOT NULL AND attribution_note IS NOT NULL"
            )
            moved = cur.fetchall()
        by_type: dict[str, int] = {}
        matched = []
        for r in rows:
            tipo, note = _classify(r["composer"])
            if tipo and not r["attribution_type"]:
                by_type[tipo] = by_type.get(tipo, 0) + 1
                matched.append((int(r["id"]), tipo, note))
        # corrección: re-clasificar las ya movidas por su nota (p.ej. unknown != anónimo)
        corrected = []
        for r in moved:
            tipo, note = _classify(r["attribution_note"])
            if tipo and tipo != r["attribution_type"]:
                corrected.append((int(r["id"]), tipo))

        print(f"=== BACKFILL ATRIBUCIÓN ({'DRY-RUN' if args.dry_run else 'EJECUTANDO'}) ===")
        print(f"  obras a mover: {len(matched)} | a corregir: {len(corrected)}")
        for t, n in sorted(by_type.items()):
            print(f"  {t:12}: {n}")
        if not args.dry_run:
            with conn.cursor() as cur:
                for wid, tipo, note in matched:
                    cur.execute(
                        "UPDATE works SET attribution_type=%s, attribution_note=%s, "
                        "composer=NULL, composer_id=NULL WHERE id=%s",
                        (tipo, note[:255], wid),
                    )
                for wid, tipo in corrected:
                    cur.execute(
                        "UPDATE works SET attribution_type=%s WHERE id=%s",
                        (tipo, wid),
                    )
                conn.commit()
            print(f"\n  aplicado: {len(matched)} movidas + {len(corrected)} corregidas")
        else:
            print("\n  muestra (a mover):")
            for wid, tipo, note in matched[:10]:
                print(f"     {wid}  {tipo:12}  {note[:50]}")
            print("  muestra (a corregir):")
            for wid, tipo in corrected[:10]:
                print(f"     {wid} -> {tipo}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
