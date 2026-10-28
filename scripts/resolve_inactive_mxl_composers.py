"""Resuelve compositores MXL desactivados usando sus obras y Gemini.

Lee personas `mxl_metadata` inactivas, envía nombre + títulos de obras a Gemini y, si hay
un compositor claro, renombra/activa o fusiona y reasocia las obras. Tradicionales se dejan
inactivas. Uso: `python scripts/resolve_inactive_mxl_composers.py [--apply]`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from validate_cleanup_ai import _call, _keys, _parse  # noqa: E402


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _db():
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    if conf.get("host") not in {"127.0.0.1", "localhost"}:
        raise SystemExit("rechazado: host no local")
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
    cur.execute(
        "UPDATE persons SET persons_status='merged', persons_merged_into=%s, "
        "persons_merged_at=NOW(6), persons_visible=0, persons_updated_at=NOW(6) "
        "WHERE persons_id=%s",
        (target, fake),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=15)
    ap.add_argument("--min-confidence", type=float, default=0.8)
    args = ap.parse_args()
    keys = _keys()
    if not keys:
        raise SystemExit("No hay clave Gemini")
    conn = _db()
    resolved = reassociated = traditional = manual = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT p.persons_id, p.persons_name, "
                "GROUP_CONCAT(DISTINCT w.works_title SEPARATOR ' || ') titles, "
                "GROUP_CONCAT(DISTINCT w.id SEPARATOR ',') work_ids "
                "FROM persons p "
                "LEFT JOIN representation_persons rp ON rp.representation_persons_person_id=p.persons_id "
                "LEFT JOIN representations r ON r.id=rp.representation_persons_representation_id "
                "LEFT JOIN works w ON w.id=r.representations_works_id "
                "WHERE p.persons_source_system='mxl_metadata' "
                "AND p.persons_status IN ('inactive','rejected') "
                "GROUP BY p.persons_id, p.persons_name"
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT persons_id, persons_name FROM persons "
                "WHERE persons_status!='merged' AND persons_type='person'"
            )
            people: dict[str, list[str]] = defaultdict(list)
            for p in cur.fetchall():
                people[_norm(p["persons_name"])].append(p["persons_id"])

            decisions: dict[str, dict[str, Any]] = {}
            for start in range(0, len(rows), args.batch):
                chunk = rows[start : start + args.batch]
                items = [
                    {
                        "persons_id": r["persons_id"],
                        "invalid_name": r["persons_name"],
                        "work_titles": [t.strip() for t in (r.get("titles") or "").split(" || ") if t.strip()][:5],
                    }
                    for r in chunk
                ]
                prompt = (
                    "Eres musicólogo. El nombre de compositor es inválido. Usa los títulos de las "
                    "obras para identificar al compositor real solo si hay evidencia clara. Si son "
                    "obras tradicionales/folclóricas sin compositor, action=traditional. No inventes. "
                    "Devuelve un array JSON con persons_id, composer (string|null), confidence "
                    "(0-1), action (rename|traditional|manual), reason.\n"
                    + json.dumps(items, ensure_ascii=False)
                )
                last = None
                for attempt in range(3):
                    try:
                        found = _parse(_call(prompt, keys[attempt % len(keys)]))
                        decisions.update({str(d["persons_id"]): d for d in found})
                        break
                    except Exception as exc:  # noqa: BLE001
                        last = exc
                else:
                    raise RuntimeError(last)
                print(f"lote {start}/{len(rows)}", flush=True)

            for row in rows:
                decision = decisions.get(str(row["persons_id"]), {})
                composer = str(decision.get("composer") or "").strip()
                action = decision.get("action")
                confidence = float(decision.get("confidence") or 0)
                if action != "rename" or not composer or confidence < args.min_confidence:
                    if action == "traditional":
                        traditional += 1
                        if args.apply:
                            cur.execute(
                                "UPDATE persons SET persons_review_reason='tradicional/anonima' "
                                "WHERE persons_id=%s",
                                (row["persons_id"],),
                            )
                    else:
                        manual += 1
                    continue
                targets = [p for p in people.get(_norm(composer), []) if p != row["persons_id"]]
                if len(targets) > 1:
                    manual += 1
                    continue
                target = targets[0] if targets else row["persons_id"]
                if args.apply:
                    if target == row["persons_id"]:
                        cur.execute(
                            "UPDATE persons SET persons_name=%s, persons_status='active', "
                            "persons_visible=1, persons_review_status='not_reviewed', "
                            "persons_updated_at=NOW(6) WHERE persons_id=%s",
                            (composer, target),
                        )
                    else:
                        _merge(cur, row["persons_id"], target)
                    for wid in [int(x) for x in (row.get("work_ids") or "").split(",") if x]:
                        cur.execute(
                            "SELECT r.works_person_roles_person_id p, p.persons_status s, "
                            "p.persons_type t FROM works_person_roles r "
                            "LEFT JOIN persons p ON p.persons_id=r.works_person_roles_person_id "
                            "WHERE r.works_person_roles_work_id=%s "
                            "AND r.works_person_roles_role_id=1",
                            (wid,),
                        )
                        role = cur.fetchone()
                        if role and role.get("s") != "merged" and role.get("t") == "person" and role.get("p") != target:
                            continue
                        cur.execute(
                            "INSERT INTO works_person_roles "
                            "(works_person_roles_work_id, works_person_roles_person_id, works_person_roles_role_id) "
                            "VALUES (%s,%s,1) ON DUPLICATE KEY UPDATE "
                            "works_person_roles_person_id=VALUES(works_person_roles_person_id)",
                            (wid, target),
                        )
                        reassociated += 1
                resolved += 1
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    print(
        f"inactivos={len(rows)} resueltos={resolved} obras_reasociadas={reassociated} "
        f"tradicionales={traditional} manuales={manual}"
    )
    print("BD actualizada" if args.apply else "DRY-RUN: usa --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
