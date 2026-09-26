"""Separa la TONALIDAD pegada al nombre de la persona y la devuelve a la obra.

En los datos hay tonos dentro de `persons_name` ("B minor Jeremiah Ingalls", "Jeremiah Ingalls
G Major", "Phrygian Mode D minor"). El tono es un dato de la OBRA (`works_musical_key`), no del
autor. Este script, para TODAS las personas (sin filtrar por rol ni estado):

1. extrae el tono (modo + tonalidad) del nombre,
2. limpia el nombre quitando ese tramo,
3. si el nombre restante es plausible, lo escribe,
4. rellena `works_musical_key` de sus obras **solo si está vacío**.

    .venv\\Scripts\\python.exe scripts/split_tonality_from_person.py
    .venv\\Scripts\\python.exe scripts/split_tonality_from_person.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pymysql  # noqa: E402
import yaml  # noqa: E402

_MODES = r"(?:Phrygian|Dorian|Lydian|Mixolydian|Aeolian|Ionian|Locrian)"
_KEY = r"[A-G](?:\s*(?:#|b|♯|♭|sharp|flat))?"
_QUALITY = (
    r"(?:major|minor|maj\.?|min\.?|majeure|mineur|dur|moll|mayor|menor|maggiore|minore)"
)
_P_HYPHEN = re.compile(
    rf"\b(?P<key>{_KEY})\s*[-\u2010-\u2015]\s*(?P<qual>{_QUALITY})\b", re.IGNORECASE
)
_P_MODE_KEY = re.compile(
    rf"\b(?P<mode>{_MODES})\s+mode\s+(?P<key>{_KEY})\s*(?P<qual>{_QUALITY})?\b",
    re.IGNORECASE,
)
_P_MODE = re.compile(rf"\b(?P<mode>{_MODES})\s+mode\b", re.IGNORECASE)
_P_KEY = re.compile(rf"\b(?P<key>{_KEY})\s+(?P<qual>{_QUALITY})\b", re.IGNORECASE)
_SEP = re.compile(r"^[\s:;,\-–—.]+|[\s:;,\-–—]+$")
# Palabras de TÍTULO: si aparecen, el registro es un título (o híbrido) y NO se toca aquí.
_TITLE_WORDS = re.compile(
    r"(?i)\b(kyrie|deus|magnificat|benedictus|jubilate|te deum|transcripted|transposed|revised|"
    r"livre|chansons|harmony|catalogue|edition|arr\.?|arranged|opus|op\.?|vol\.?|mass|creed|"
    r"nicene|trio|quartet|clarinet|piano)\b"
)
_CONNECTORS = re.compile(r"(?i)\b(in|to|of|de|del|la|le|el|y|and|or|the|a|an|pour|par)\b\s*$")
_TONALITY_LEFTOVER = re.compile(
    r"(?i)(major|minor|majeur|mineur|dur|moll|mayor|menor|ionian|phrygian|dorian|lydian|"
    r"mixolydian|aeolian|locrian|\bmode\b)"
    r"|\b[A-H](?:\s*(?:#|b|♯|♭))?\s*(?:major|minor|maj|min)"
)
_QUALITY_FIX = {
    "maj": "major", "maj.": "major", "majeure": "major", "dur": "major", "mayor": "major",
    "maggiore": "major", "min": "minor", "min.": "minor", "mineur": "minor", "moll": "minor",
    "menor": "minor", "minore": "minor",
}
_KEY_FIX = {"bb": "B♭", "eb": "E♭", "ab": "A♭", "gb": "G♭", "db": "D♭", "b": "B"}


def _norm_tonality(mode: str, key: str, qual: str) -> str:
    key = re.sub(r"\s+", " ", key or "").strip()
    low = key.lower().replace(" flat", "b").replace(" sharp", "#")
    key = _KEY_FIX.get(low, low.capitalize() if len(low) == 1 else low)
    qual = _QUALITY_FIX.get((qual or "").lower().rstrip("."), (qual or "").lower())
    text = f"{key} {qual}".strip() if qual else key
    return f"{text} ({mode})" if mode else text


def _person_like(text: str) -> bool:
    if not text or _TITLE_WORDS.search(text) or _CONNECTORS.search(text):
        return False
    if _TONALITY_LEFTOVER.search(text):
        return False
    if re.search(r"^[a-zà-ÿ]+\b", text):
        return False
    if re.search(r"\s[-–—]\s", text):
        return False
    if _spans(text):
        return False
    if any(ch.isdigit() for ch in text) or "/" in text or ":" in text:
        return False
    tokens = re.findall(r"[^\W\d_][\w'’.\-]*", text, re.UNICODE)
    return len(tokens) >= 2


def _spans(name: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for match in _P_MODE_KEY.finditer(name):
        spans.append((match.start(), match.end(),
                      _norm_tonality(match.group("mode").title(), match.group("key"),
                                     match.group("qual") or "")))
    for pattern in (_P_HYPHEN, _P_KEY):
        for match in pattern.finditer(name):
            if any(s <= match.start() < e for s, e, _ in spans):
                continue
            spans.append((match.start(), match.end(),
                          _norm_tonality("", match.group("key"), match.group("qual"))))
    for match in _P_MODE.finditer(name):
        if any(s <= match.start() < e for s, e, _ in spans):
            continue
        spans.append((match.start(), match.end(), _norm_tonality(match.group("mode").title(), "", "")))
    return sorted(spans)


def _extract(name: str) -> tuple[str, str]:
    """Devuelve (nombre_sin_tono, tono). Vacío si no procede limpiar."""
    spans = _spans(name)
    if not spans:
        return name, ""
    tonality = spans[0][2]
    text = name
    for start, end, _ in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    text = _SEP.sub("", re.sub(r"\s+", " ", text)).strip()
    if not _person_like(text):
        return name, ""
    return text, tonality


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
            cur.execute("SELECT persons_id, persons_name FROM persons")
            people = cur.fetchall()
        found: list[tuple[str, str, str, str]] = []
        for person in people:
            cleaned, tonality = _extract(str(person["persons_name"] or ""))
            if tonality and cleaned and cleaned != person["persons_name"]:
                found.append((str(person["persons_id"]), cleaned, str(person["persons_name"]),
                              tonality))
        print(f"personas: {len(people)}  con tono en el nombre: {len(found)}")
        for pid, cleaned, original, tonality in found[:15]:
            print(f"  {original[:62]!r}\n      -> {cleaned[:52]!r}  tono={tonality!r}")
        dist = Counter(t for *_, t in found)
        print("tonos:", dict(dist.most_common(10)))
        if not args.apply:
            print("DRY-RUN: usa --apply para escribir.")
            return 0
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE persons SET persons_name=%s WHERE persons_id=%s",
                [(cleaned, pid) for pid, cleaned, _, _ in found],
            )
            filled = 0
            for pid, _, _, tonality in found:
                cur.execute(
                    "SELECT works_person_roles_work_id AS work_id FROM works_person_roles"
                    " WHERE works_person_roles_person_id=%s AND works_person_roles_role_id=1",
                    (pid,),
                )
                for row in cur.fetchall():
                    cur.execute(
                        "UPDATE works SET works_musical_key=%s WHERE id=%s"
                        " AND (works_musical_key IS NULL OR works_musical_key='')",
                        (tonality, row["work_id"]),
                    )
                    filled += cur.rowcount
            print(f"nombres corregidos: {len(found)}  obras con tonalidad rellenada: {filled}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
