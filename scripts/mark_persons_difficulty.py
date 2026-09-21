"""Marca `persons_review_status` por DIFICULTAD de revisión (not_reviewed_1/2/3).

Se apoya en la clasificación de `clean_persons_v2` (mismas reglas) y asigna:

- `reviewed`        : sin incidencias (o solo anotación recortada, ya aplicada).
- `not_reviewed_1`  : **fácil** — parece persona, solo hay que ajustar el split.
- `not_reviewed_2`  : **medio** — grupos/dúos (`and/y/&`), múltiples (`;`) o registros que
                      probablemente NO son personas (títulos, `file ID:`, rutas…).
- `not_reviewed_3`  : **difícil** — mojibake/CJK: hay que ir a la obra y su MusicXML.

Idempotente. Solo cambia el estado (no toca nombre ni roles, por eso no requiere historial):

    .venv\\Scripts\\python.exe scripts/mark_persons_difficulty.py            # dry-run
    .venv\\Scripts\\python.exe scripts/mark_persons_difficulty.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from clean_persons_v2 import _parse  # noqa: E402

_PERSON_LIKE = re.compile(r"^[^\W\d_][\w'’.\-]*(\s+[^\W\d_][\w'’.\-]*){0,7}$", re.UNICODE)


def _looks_like_person(name: str) -> bool:
    """Nombre plausible: sin dígitos, sin rutas ni ':', 1–8 tokens alfabéticos."""
    if any(ch.isdigit() for ch in name) or "/" in name or ":" in name:
        return False
    return bool(_PERSON_LIKE.match(name.strip()))


def _level(row: dict) -> str:
    flags = set(row["flags"])
    if "irrepresentable" in flags:
        return "not_reviewed_3"
    if "revisar_agrupacion" in flags or "multiple" in flags:
        return "not_reviewed_2"
    if "revisar_split" in flags:
        return "not_reviewed_1" if _looks_like_person(row["name"] or "") else "not_reviewed_2"
    return "reviewed"


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with open(ROOT / "config.yaml", encoding="utf-8") as handle:
        conf = (yaml.safe_load(handle) or {}).get("db") or {}
    conn = pymysql.connect(
        host=conf.get("host", "127.0.0.1"), port=int(conf.get("port", 3306)),
        user=conf.get("user"), password=conf.get("password"),
        database=conf.get("name") or conf.get("database"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT persons_id, persons_name, persons_review_status FROM persons")
            people = cur.fetchall()
        target: dict[str, str] = {}
        dist: Counter[str] = Counter()
        samples: dict[str, list[str]] = {}
        for person in people:
            row = _parse(person["persons_name"])
            level = _level(row)
            dist[level] += 1
            if len(samples.setdefault(level, [])) < 4:
                samples[level].append(str(person["persons_name"])[:58])
            if str(person["persons_review_status"] or "") != level:
                target[str(person["persons_id"])] = level
        print(f"personas: {len(people)}")
        for level, count in dist.most_common():
            print(f"  {level}: {count}")
            for name in samples[level]:
                print(f"      {name!r}")
        print(f"cambios de estado: {len(target)}")
        if not args.apply:
            print("DRY-RUN: usa --apply para marcar persons_review_status.")
            return 0
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE persons SET persons_review_status=%s WHERE persons_id=%s",
                [(level, pid) for pid, level in target.items()],
            )
        print(f"aplicado: {len(target)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
