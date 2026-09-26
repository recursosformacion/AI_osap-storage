"""Limpieza de CARACTERES en TODAS las personas (`persons.persons_name`), sin filtrar por rol
ni por estado de revisión. Reglas deterministas, sin decisiones semánticas:

- NFKC, fuera controles y caracteres de ancho cero.
- Espacios: colapsar, recortar, quitar espacio antes de `,`.
- Falta de espacio tras paréntesis: `)Paul` -> `) Paul`.
- Años pegados: `(1810 1873)` -> `(1810-1873)`; `(18501922)` -> `(1850-1922)`.
- Mojibake real por secuencia Latin-1 mal decodificada (`Ã©`->`é`, `Å‚`->`ł`, ...).
  CJK/cirílico/griego NO son mojibake: no se tocan.

    .venv\\Scripts\\python.exe scripts/clean_person_names_chars.py
    .venv\\Scripts\\python.exe scripts/clean_person_names_chars.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pymysql  # noqa: E402
import yaml  # noqa: E402

_CONTROL = re.compile(r"[\u0000-\u001f\u007f\u200b-\u200f\u2060\ufeff]")
_AFTER_PAREN = re.compile(r"([)\]])(?=[A-ZÀ-Þ\u00c0-\u024f])")
_JOIN_WORD = re.compile(r"\)(?=(?i:and|or|und|y|et)\b)")
_YEARS_JOIN = re.compile(r"\((\d{4})\s+(\d{4})\)")
_YEARS_GLUED = re.compile(r"\((1[0-9]{3})(1[0-9]{3})\)")
_SPACE_BEFORE_COMMA = re.compile(r"\s+,")
_GLUED_PREP = re.compile(r"(?<=[àèìòù])(?=[A-ZÀ-Þ][a-zà-ÿ]{2,})")
_MOJIBAKE_MAP = (
    ("Ã©", "é"), ("Ã¨", "è"), ("Ã¡", "á"), ("Ã ", "à"), ("Ã³", "ó"), ("Ãº", "ú"),
    ("Ã­", "í"), ("Ã±", "ñ"), ("Ã¼", "ü"), ("Ã¶", "ö"), ("Ã¤", "ä"), ("Ã§", "ç"),
    ("Ãµ", "õ"), ("Ãª", "ê"), ("Ã´", "ô"), ("Ã¢", "â"), ("Ã®", "î"), ("Ã»", "û"),
    ("Ã«", "ë"), ("Ã¯", "ï"), ("Ã‰", "É"), ("Ã ", "à "),
    ("Å‚", "ł"), ("Å›", "ś"), ("Å¼", "ż"), ("Åº", "ź"), ("Å„", "ń"),
    ("Ä…", "ą"), ("Ä™", "ę"), ("Â·", "·"), ("â€™", "’"), ("â€˜", "‘"),
    ("â€œ", "“"), ("â€\x9d", "”"), ("â€“", "–"), ("â€”", "—"), ("Â ", " "),
)


def _clean(raw: str) -> tuple[str, set[str]]:
    rules: set[str] = set()
    text = unicodedata.normalize("NFKC", str(raw or ""))
    if _CONTROL.search(text):
        text = _CONTROL.sub("", text)
        rules.add("control")
    for bad, good in _MOJIBAKE_MAP:
        if bad in text:
            text = text.replace(bad, good)
            rules.add("mojibake")
    if _YEARS_GLUED.search(text):
        text = _YEARS_GLUED.sub(r"(\1-\2)", text)
        rules.add("anios_pegados")
    if _YEARS_JOIN.search(text):
        text = _YEARS_JOIN.sub(r"(\1-\2)", text)
        rules.add("anios_sin_guion")
    if _AFTER_PAREN.search(text):
        text = _AFTER_PAREN.sub(r"\1 ", text)
        rules.add("espacio_tras_parentesis")
    if _JOIN_WORD.search(text):
        text = _JOIN_WORD.sub(") ", text)
        rules.add("espacio_tras_parentesis")
    if _GLUED_PREP.search(text):
        text = _GLUED_PREP.sub(" ", text)
        rules.add("preposicion_pegada")
    if _SPACE_BEFORE_COMMA.search(text):
        text = _SPACE_BEFORE_COMMA.sub(",", text)
        rules.add("espacio_antes_coma")
    collapsed = re.sub(r"\s+", " ", text).strip()
    if collapsed != text:
        rules.add("espacios")
    return collapsed, rules


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
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
            cur.execute("SELECT persons_id, persons_name FROM persons")
            people = cur.fetchall()
        changes: list[tuple[str, str, str]] = []
        dist: Counter[str] = Counter()
        samples: dict[str, list[str]] = {}
        for person in people:
            new, rules = _clean(person["persons_name"])
            if new and new != person["persons_name"]:
                changes.append((str(person["persons_id"]), new, str(person["persons_name"])))
                for rule in rules:
                    dist[rule] += 1
                    if len(samples.setdefault(rule, [])) < 3:
                        samples[rule].append(f"{person['persons_name']!r} -> {new!r}")
        print(f"personas: {len(people)}  con cambios: {len(changes)}")
        for rule, count in dist.most_common():
            print(f"  {rule}: {count}")
            for sample in samples[rule]:
                print(f"      {sample}")
        if args.limit:
            changes = changes[: args.limit]
        if not args.apply:
            print("DRY-RUN: usa --apply para escribir.")
            return 0
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE persons SET persons_name=%s WHERE persons_id=%s",
                [(new, pid) for pid, new, _ in changes],
            )
        print(f"actualizadas: {len(changes)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
