"""Genera un lote de revisiones IA para nombres con la TONALIDAD pegada ("D minorOliver Holden").

Lee las fichas visibles en rol 1, separa `«Tonalidad» + «Persona»` y emite un JSON para
`apply_ai_composer_reviews.py` con la canonicalización a la persona existente y `set_key`
para rellenar `works_musical_key` de esas obras.

    .venv\\Scripts\\python.exe scripts/gen_key_glued_batch.py docs/ai/reviews_keys.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pymysql  # noqa: E402
import yaml  # noqa: E402

_KEY = re.compile(
    r"^(?P<key>[A-G])\s*(?P<acc>#|b|\u266f|\u266d)?\s*"
    r"(?P<qual>(?i:major|minor|maj|min))\s*(?P<person>[A-Z][^\s].*)$"
)
_QUALITY = {"major": "major", "maj": "major", "minor": "minor", "min": "minor"}
_REVISED = re.compile(r"(?i)\s*(revised|rev\.?|version)\s*$")


def _norm(text: str) -> str:
    import unicodedata

    flat = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", flat).split())


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/ai/reviews_keys.json"
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
            cur.execute("SELECT persons_name FROM persons")
            by_norm: dict[str, str] = {}
            for row in cur.fetchall():
                by_norm.setdefault(_norm(row["persons_name"]), str(row["persons_name"]))
            cur.execute(
                "SELECT p.persons_name n, COUNT(*) w FROM persons p JOIN works_person_roles r"
                " ON r.works_person_roles_person_id=p.persons_id"
                " WHERE r.works_person_roles_role_id=1 AND p.persons_visible=1"
                " GROUP BY n"
            )
            batch: list[dict[str, str]] = []
            skipped: list[str] = []
            for row in cur.fetchall():
                match = _KEY.match(str(row["n"]).strip())
                if not match:
                    continue
                person_raw = _REVISED.sub("", match.group("person")).strip()
                person = by_norm.get(_norm(person_raw))
                if not person or person == row["n"]:
                    skipped.append(str(row["n"]))
                    continue
                key = f"{match.group('key')}{match.group('acc') or ''} " \
                      f"{_QUALITY[match.group('qual').lower()]}"
                key = key.replace("b ", "\u266d ").replace("# ", "\u266f ")
                batch.append(
                    {"name": str(row["n"]), "action": "canonicalize", "canonical": person,
                     "set_key": key}
                )
            out_path.write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"lote: {len(batch)} entradas -> {out_path}")
            print(f"sin persona canónica ({len(skipped)}): {skipped[:6]}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
