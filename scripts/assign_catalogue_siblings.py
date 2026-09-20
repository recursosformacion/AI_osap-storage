"""Asigna compositor (rol 1) a obras sin atribución usando obras HERMANAS de catálogo.

Regla determinista y reversible: si varias obras comparten el **mismo catálogo**
(comparado en mayúsculas y sin espacios sobrantes) y **exactamente una** de ellas tiene
compositor (rol 1 en `works_person_roles`), se copia esa persona a las hermanas que no lo
tienen. Si hay varios compositores distintos entre las hermanas, NO se toca (ambiguo).

Idempotente. Reversible: los inserts quedan auditados en `works_person_roles_history` si la
tabla existe (operation='assign'); `--revert` borra los rol-1 creados por este script.

    .venv\\Scripts\\python.exe scripts/assign_catalogue_siblings.py            # dry-run
    .venv\\Scripts\\python.exe scripts/assign_catalogue_siblings.py --apply
    .venv\\Scripts\\python.exe scripts/assign_catalogue_siblings.py --revert
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

SOURCE = "catalogue-sibling"
SOURCE_TITLE = "title-sibling"


def _title_key(raw: str | None) -> str:
    from domain.services.composer_names import normalize_composer_name as norm

    return norm(str(raw or ""))


def _assign(
    cur: object,
    proposals: list[dict],
    owners: dict[str, str],
    key_field: str,
    source: str,
    history: bool,
    apply: bool,
) -> int:
    applied = 0
    for row in proposals:
        key = str(row[key_field])
        if key not in owners:
            continue
        if not apply:
            applied += 1
            continue
        cur.execute(
            "INSERT INTO works_person_roles (works_person_roles_work_id, "
            "works_person_roles_person_id, works_person_roles_role_id, works_person_roles_order) "
            "VALUES (%s,%s,1,0)",
            (row["id"], owners[key]),
        )
        if history:
            cur.execute(
                "INSERT INTO works_person_roles_history (works_person_roles_id, work_id, person_id, "
                "role_id, works_person_roles_order, operation, batch_id, created_at) "
                "VALUES (%s,%s,%s,1,0,'assign',%s,NOW())",
                (cur.lastrowid, row["id"], owners[key], source),
            )
        applied += 1
    return applied


def _norm_catalogue(raw: str | None) -> str:
    """Clave de catálogo comparable: minúsculas, sin acentos, prefijos unificados y
    separación letra/número ("BWV479" == "bwv 479" == "BWV 479")."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", str(raw or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"(?<=\D)(?=\d)", " ", text)
    tokens = [t for t in re.split(r"[^a-z0-9]+", text) if t]
    if not tokens:
        return ""
    aliases = {"kv": "k", "opus": "op", "no": "no", "nr": "no", "num": "no"}
    tokens[0] = aliases.get(tokens[0], tokens[0])
    return " ".join(tokens)


def _db() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    conf = cfg.get("db") or cfg.get("database") or {}
    return {
        "host": conf.get("host", "127.0.0.1"),
        "port": int(conf.get("port", 3306)),
        "user": conf.get("user"),
        "password": conf.get("password"),
        "database": conf.get("name") or conf.get("database"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--revert", action="store_true", help="borra las asignaciones de este script")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    conn = pymysql.connect(**_db(), charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                           autocommit=True)
    try:
        with conn.cursor() as cur:
            if args.revert:
                cur.execute(
                    "DELETE FROM works_person_roles WHERE works_person_roles_role_id = 1 "
                    "AND works_person_roles_id IN (SELECT works_person_roles_id FROM "
                    "works_person_roles_history WHERE operation='assign' AND source=%s)",
                    (SOURCE,),
                )
                print(f"revertidas: {cur.rowcount}")
                return 0

            # 1) Compositor(es) por catálogo NORMALIZADO (solo obras con atribución).
            cur.execute(
                "SELECT w.works_catalogue AS cat, r.works_person_roles_person_id AS persona "
                "FROM works w JOIN works_person_roles r "
                "  ON r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1 "
                "WHERE w.works_catalogue IS NOT NULL AND TRIM(w.works_catalogue) <> ''"
            )
            by_key: dict[str, set[str]] = {}
            for row in cur.fetchall():
                key = _norm_catalogue(row["cat"])
                if key and row["persona"]:
                    by_key.setdefault(key, set()).add(str(row["persona"]))
            owners = {key: next(iter(personas)) for key, personas in by_key.items() if len(personas) == 1}
            ambiguous = sum(1 for personas in by_key.values() if len(personas) > 1)
            print(f"catálogos con compositor único: {len(owners)} (ambiguos: {ambiguous})")

            # 2) Obras sin rol 1 cuyo catálogo (normalizado) tiene compositor único.
            cur.execute(
                "SELECT w.id, w.works_catalogue AS cat, w.works_title AS title "
                "FROM works w "
                "WHERE w.works_catalogue IS NOT NULL AND TRIM(w.works_catalogue) <> '' "
                "AND NOT EXISTS (SELECT 1 FROM works_person_roles r "
                "  WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1)"
            )
            proposals = []
            for row in cur.fetchall():
                key = _norm_catalogue(row["cat"])
                if key in owners:
                    row["key"] = key
                    proposals.append(row)
            if args.limit:
                proposals = proposals[: args.limit]
            print(f"propuestas: {len(proposals)}")
            for row in proposals[:5]:
                print(f"  work={row['id']} cat={row['key']!r} -> {owners[row['key']]}")
            if not args.apply:
                print("DRY-RUN: usa --apply para escribir.")
                return 0

            history = False
            with contextlib.suppress(pymysql.err.ProgrammingError):
                cur.execute("SELECT 1 FROM works_person_roles_history LIMIT 1")
                history = True
            applied = _assign(cur, proposals, owners, "key", SOURCE, history, True)
            print(f"aplicado (catálogo): {applied}")

            # 3) Hermanas por TÍTULO normalizado idéntico (misma pieza en otra fuente).
            cur.execute(
                "SELECT w.id, w.works_title AS title FROM works w "
                "WHERE TRIM(COALESCE(w.works_title,'')) <> '' "
                "AND NOT EXISTS (SELECT 1 FROM works_person_roles r "
                "  WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1)"
            )
            missing_titles = [
                {"id": row["id"], "title_key": _title_key(row["title"])} for row in cur.fetchall()
            ]
            cur.execute(
                "SELECT w.works_title AS title, r.works_person_roles_person_id AS persona "
                "FROM works w JOIN works_person_roles r "
                "  ON r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1"
            )
            by_title: dict[str, set[str]] = {}
            for row in cur.fetchall():
                key = _title_key(row["title"])
                if key and row["persona"]:
                    by_title.setdefault(key, set()).add(str(row["persona"]))
            title_owners = {k: next(iter(v)) for k, v in by_title.items() if len(v) == 1}
            applied_title = _assign(
                cur, missing_titles, title_owners, "title_key", SOURCE_TITLE, history, True
            )
            print(f"aplicado (título): {applied_title}")
            print(f"total: {applied + applied_title}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
