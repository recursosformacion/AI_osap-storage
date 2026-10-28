"""Sanea los compositores creados desde MXL: limpia puntuación inicial, fusiona con una
persona existente cuando el nombre limpio coincide y desactiva los nombres que no son personas.

No se aplica a toda la base: solo a `persons_source_system='mxl_metadata'`.
Uso dev:
    .venv\\Scripts\\python.exe scripts/sanitize_mxl_persons.py
    .venv\\Scripts\\python.exe scripts/sanitize_mxl_persons.py --apply
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
BAD = re.compile(
    r"(?i)\b(anon|unknown|trad|folk song|folk hymn|popular dance|transcribed|arranged|"
    r"collection|untitled|hand|ms\.?|no\s*\d+|vor\s*\d+|urheber|volksweise|"
    r"a\s+country\s+dance|country\s+dance)\b"
)


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _clean(value: str) -> str:
    text = (value or "").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = re.sub(r"^[\s:;\"'`.,\-–—]+", "", text)
    text = re.sub(r"[\s:;\"'`.,\-–—]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _bad(name: str) -> bool:
    if len(name) < 4 or len(name) > 80:
        return True
    if not re.search(r"[A-Za-zÀ-ÿ]", name):
        return True
    return bool(BAD.search(name))


def _db():
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    return pymysql.connect(
        host=conf["host"],
        port=conf["port"],
        user=conf["user"],
        password=conf["password"],
        database=conf["name"],
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


def _merge(cur, fake: str, target: str) -> None:
    cur.execute("SELECT * FROM works_person_roles WHERE works_person_roles_person_id=%s", (fake,))
    for row in cur.fetchall():
        cur.execute(
            "SELECT works_person_roles_id FROM works_person_roles "
            "WHERE works_person_roles_work_id=%s AND works_person_roles_role_id=%s "
            "AND works_person_roles_person_id=%s",
            (row["works_person_roles_work_id"], row["works_person_roles_role_id"], target),
        )
        if cur.fetchone():
            cur.execute(
                "DELETE FROM works_person_roles WHERE works_person_roles_id=%s",
                (row["works_person_roles_id"],),
            )
        else:
            cur.execute(
                "UPDATE works_person_roles SET works_person_roles_person_id=%s WHERE works_person_roles_id=%s",
                (target, row["works_person_roles_id"]),
            )
    cur.execute("SELECT id FROM persons_identity WHERE persons_id=%s", (fake,))
    for row in cur.fetchall():
        cur.execute(
            "SELECT id FROM persons_identity WHERE persons_id=%s AND identity_type=%s AND identity_value=%s LIMIT 1",
            (target, row["identity_type"], row["identity_value"]),
        )
        if cur.fetchone():
            cur.execute("DELETE FROM persons_identity WHERE id=%s", (row["id"],))
        else:
            cur.execute("UPDATE persons_identity SET persons_id=%s WHERE id=%s", (target, row["id"]))
    cur.execute(
        "UPDATE persons SET persons_status='merged', persons_merged_into=%s, "
        "persons_merged_at=NOW(6), persons_visible=0, persons_updated_at=NOW(6) "
        "WHERE persons_id=%s",
        (target, fake),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    conn = _db()
    renamed = merged = deactivated = manual = 0
    try:
        with conn.cursor() as cur:
            if args.all:
                cur.execute(
                    "SELECT persons_id, persons_name FROM persons "
                    "WHERE persons_status!='merged' AND "
                    "(persons_source_system='mxl_metadata' OR "
                    "persons_name REGEXP '^[[:space:][:punct:]]')"
                )
            else:
                cur.execute(
                    "SELECT persons_id, persons_name FROM persons "
                    "WHERE persons_source_system='mxl_metadata' AND persons_status!='merged'"
                )
            rows = cur.fetchall()
            cur.execute(
                "SELECT persons_id, persons_name FROM persons WHERE persons_status!='merged' AND persons_type='person'"
            )
            people: dict[str, list[str]] = {}
            for p in cur.fetchall():
                people.setdefault(_norm(p["persons_name"]), []).append(p["persons_id"])

            for row in rows:
                name = _clean(str(row["persons_name"]))
                if " - " in name:
                    manual += 1
                    if args.apply:
                        cur.execute(
                            "UPDATE persons SET persons_visible=0, persons_review_status='not_reviewed', "
                            "persons_review_reason='nombre con varios compositores' WHERE persons_id=%s",
                            (row["persons_id"],),
                        )
                    continue
                if _bad(name):
                    deactivated += 1
                    if args.apply:
                        cur.execute(
                            "DELETE FROM works_person_roles WHERE works_person_roles_person_id=%s "
                            "AND works_person_roles_role_id=1",
                            (row["persons_id"],),
                        )
                        cur.execute(
                            "UPDATE persons SET persons_visible=0, persons_status='inactive', "
                            "persons_review_status='rejected', "
                            "persons_review_reason='nombre no identificable como persona' WHERE persons_id=%s",
                            (row["persons_id"],),
                        )
                    continue
                targets = [p for p in people.get(_norm(name), []) if p != row["persons_id"]]
                if len(targets) == 1:
                    merged += 1
                    if args.apply:
                        _merge(cur, row["persons_id"], targets[0])
                    continue
                if len(targets) > 1:
                    manual += 1
                    continue
                if name != row["persons_name"]:
                    renamed += 1
                    if args.apply:
                        cur.execute(
                            "UPDATE persons SET persons_name=%s, persons_updated_at=NOW(6) WHERE persons_id=%s",
                            (name, row["persons_id"]),
                        )
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    print(f"mxl={len(rows)} renombrados={renamed} fusionados={merged} desactivados={deactivated} manuales={manual}")
    print("BD actualizada" if args.apply else "DRY-RUN: usa --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
