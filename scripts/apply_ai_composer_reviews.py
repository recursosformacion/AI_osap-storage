"""Aplica un lote de revisiones IA de compositores: nombre + biografía.

Entrada: un JSON (lista) producido por la revisión IA, con entradas como:

    {
      "name": "Heny Purcell",
      "action": "correct",                  # correct | person_ok | duplicate | not_person
      "corrected_name": "Henry Purcell",     # solo en `correct`
      "duplicate_of": "Johann Sebastian Bach",  # solo en `duplicate`
      "summary": "...", "era": "Barroco", "nationality": "Inglesa",
      "key_works": ["Dido and Aeneas"], "key_fact": "..."
    }

Acciones:
- `correct`   : corrige `persons_name` y escribe la biografía (queda `reviewed`, visible).
- `person_ok` : escribe la biografía (nombre ya correcto).
- `duplicate` : no renombra; marca `persons_review_reason='duplicado de …'` y oculta del catálogo.
- `not_person` : no es una persona (grupo, tradicional…) -> oculta y desvincula el rol 1.

    .venv\\Scripts\\python.exe scripts/apply_ai_composer_reviews.py docs/ai/reviews_lote1.json
    .venv\\Scripts\\python.exe scripts/apply_ai_composer_reviews.py docs/ai/reviews_lote1.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pymysql  # noqa: E402
import yaml  # noqa: E402


def _norm(text: str) -> str:
    flat = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(flat.split())


def _db() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as handle:
        conf = (yaml.safe_load(handle) or {}).get("db") or {}
    return {
        "host": conf.get("host", "127.0.0.1"),
        "port": int(conf.get("port", 3306)),
        "user": conf.get("user"),
        "password": conf.get("password"),
        "database": conf.get("name") or conf.get("database"),
    }


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", help="JSON con las revisiones")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    reviews = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    conn = pymysql.connect(**_db(), charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                           autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.persons_id, p.persons_name, p.persons_visible, p.persons_biography_summary,"
                " (SELECT COUNT(*) FROM works_person_roles r WHERE r.works_person_roles_person_id=p.persons_id"
                "  AND r.works_person_roles_role_id=1) AS works"
                " FROM persons p"
            )
            by_norm: dict[str, list[dict]] = {}
            for row in cur.fetchall():
                by_norm.setdefault(_norm(row["persons_name"]), []).append(row)

            applied = {"correct": 0, "person_ok": 0, "duplicate": 0, "not_person": 0,
                       "canonicalize": 0}
            by_surname: dict[str, list[dict]] = {}
            for rows in by_norm.values():
                for row in rows:
                    tokens = _norm(row["persons_name"]).split()
                    if tokens:
                        by_surname.setdefault(tokens[-1], []).append(row)
            for entry in reviews:
                name = str(entry.get("name") or "")
                matches = by_norm.get(_norm(name), [])
                if not matches:
                    tokens = _norm(name).split()
                    candidates = by_surname.get(tokens[-1], []) if tokens else []
                    if len(candidates) == 1:
                        matches = candidates
                        print(f"  ~ {name!r} localizado por apellido:"
                              f" {candidates[0]['persons_name'][:40]!r}")
                if not matches:
                    print(f"  !! no encontrado: {name!r}")
                    continue
                if len(matches) > 1:
                    matches = sorted(matches, key=lambda m: -int(m.get("works") or 0))
                    print(f"  ~ {name!r}: {len(matches)} fichas; se usa la de más obras"
                          f" ({matches[0]['works']} obras)")
                person_id = str(matches[0]["persons_id"])
                duplicates = [str(m["persons_id"]) for m in matches[1:]]
                action = str(entry.get("action") or "person_ok")
                print(f"  {action:<10} {name[:40]!r} -> {str(entry.get('corrected_name') or '')[:40]}")
                if not args.apply:
                    applied[action] = applied.get(action, 0) + 1
                    continue
                sources = [person_id]
                if action == "canonicalize":
                    # Puede haber varias fichas con el mismo nombre: se canonicalizan todas.
                    sources = [str(m["persons_id"]) for m in matches]
                if action == "not_person":
                    for source_id in sources:
                        cur.execute(
                            "DELETE FROM works_person_roles WHERE works_person_roles_person_id=%s"
                            " AND works_person_roles_role_id=1",
                            (source_id,),
                        )
                        cur.execute(
                            "UPDATE persons SET persons_visible=0, persons_review_status='reviewed',"
                            " persons_review_reason='no es persona',"
                            " persons_reviewed_at=NOW(6) WHERE persons_id=%s",
                            (source_id,),
                        )
                elif action == "canonicalize":
                    canonical = str(entry.get("canonical") or "")
                    targets = by_norm.get(_norm(canonical), [])
                    if not targets:
                        # El canónico puede no existir todavía: se crea aquí.
                        if not args.apply:
                            print(f"      (se crearía la persona canónica {canonical!r})")
                            continue
                        target_id = str(uuid.uuid4())
                        cur.execute(
                            "INSERT INTO persons (persons_id, persons_name, persons_visible,"
                            " persons_status, persons_review_status, persons_source_system)"
                            " VALUES (%s,%s,1,'active','reviewed','ai-review')",
                            (target_id, canonical),
                        )
                        print(f"      + canónico creado {canonical!r}")
                        by_norm.setdefault(_norm(canonical), []).append(
                            {"persons_id": target_id, "persons_name": canonical, "works": 0}
                        )
                    else:
                        target = max(targets, key=lambda m: int(m.get("works") or 0))
                        target_id = str(target["persons_id"])
                    note = entry.get("note") or name
                    set_key = str(entry.get("set_key") or "").strip()
                    moved = 0
                    all_works: list[str] = []
                    for source_id in sources:
                        cur.execute(
                            "SELECT works_person_roles_work_id AS work_id,"
                            " works_person_roles_order AS ord FROM works_person_roles"
                            " WHERE works_person_roles_person_id=%s"
                            " AND works_person_roles_role_id=1",
                            (source_id,),
                        )
                        links = cur.fetchall()
                        if not links:
                            continue
                        placeholders = ",".join(["%s"] * len(links))
                        ids = [str(r["work_id"]) for r in links]
                        cur.execute(
                            "UPDATE works SET works_attribution_note=%s WHERE id IN ("
                            + placeholders
                            + ") AND (works_attribution_note IS NULL OR works_attribution_note='')",
                            (note, *ids),
                        )
                        cur.execute(
                            "DELETE FROM works_person_roles WHERE works_person_roles_person_id=%s"
                            " AND works_person_roles_role_id=1",
                            (source_id,),
                        )
                        for row in links:
                            cur.execute(
                                "SELECT 1 FROM works_person_roles WHERE"
                                " works_person_roles_work_id=%s AND"
                                " works_person_roles_person_id=%s AND"
                                " works_person_roles_role_id=1 LIMIT 1",
                                (row["work_id"], target_id),
                            )
                            if cur.fetchone():
                                continue
                            cur.execute(
                                "INSERT INTO works_person_roles (works_person_roles_work_id,"
                                " works_person_roles_person_id, works_person_roles_role_id,"
                                " works_person_roles_order) VALUES (%s,%s,1,%s)",
                                (row["work_id"], target_id, row["ord"] or 0),
                            )
                        moved += len(links)
                        all_works.extend(ids)
                        cur.execute(
                            "UPDATE persons SET persons_visible=0,"
                            " persons_review_status='reviewed', persons_review_reason=%s,"
                            " persons_reviewed_at=NOW(6) WHERE persons_id=%s",
                            (f"canonizado en {canonical}", source_id),
                        )
                    if set_key and all_works:
                        placeholders = ",".join(["%s"] * len(all_works))
                        cur.execute(
                            "UPDATE works SET works_musical_key=%s WHERE id IN ("
                            + placeholders
                            + ") AND (works_musical_key IS NULL OR works_musical_key='')",
                            (set_key, *all_works),
                        )
                    print(f"      {moved} obras ({len(sources)} fichas) -> {canonical!r};"
                          f" nota={note[:40]!r}")
                elif action == "duplicate":
                    cur.execute(
                        "UPDATE persons SET persons_visible=0, persons_review_status='reviewed',"
                        " persons_review_reason=%s, persons_reviewed_at=NOW(6)"
                        " WHERE persons_id=%s",
                        (f"duplicado de {entry.get('duplicate_of') or '?'}", person_id),
                    )
                else:
                    new_name = str(entry.get("corrected_name") or name).strip()
                    cur.execute(
                        "UPDATE persons SET persons_name=%s, persons_visible=1,"
                        " persons_review_status='reviewed', persons_review_reason=NULL,"
                        " persons_reviewed_at=NOW(6), persons_biography_summary=%s,"
                        " persons_biography_era=%s, persons_biography_nationality=%s,"
                        " persons_biography_key_works=%s, persons_biography_key_fact=%s,"
                        " persons_biography_updated_at=NOW(6) WHERE persons_id=%s",
                        (
                            new_name,
                            entry.get("summary"),
                            entry.get("era"),
                            entry.get("nationality"),
                            json.dumps(entry.get("key_works") or [], ensure_ascii=False),
                            entry.get("key_fact"),
                            person_id,
                        ),
                    )
                    # Las otras fichas con el mismo nombre son duplicados: se ocultan (no se fusionan).
                    for dup_id in duplicates:
                        cur.execute(
                            "UPDATE persons SET persons_visible=0, persons_review_status='reviewed',"
                            " persons_review_reason=%s, persons_reviewed_at=NOW(6)"
                            " WHERE persons_id=%s",
                            (f"duplicado de {new_name}", dup_id),
                        )
                    if duplicates:
                        print(f"      duplicados ocultados: {len(duplicates)}")
                applied[action] = applied.get(action, 0) + 1
            print("resumen:", applied)
        if not args.apply:
            print("DRY-RUN: usa --apply para escribir.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
