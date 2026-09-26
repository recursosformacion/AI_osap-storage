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


def _alpha_len(name: str) -> int:
    """Letras reales del nombre, sin espacios ni signos."""
    return sum(1 for ch in name if ch.isalpha())


# Anotaciones que nunca forman parte de un nombre de autor: "anged from Mozart",
# "Mozartarr Mason A", "Composed W A Mozart", "attributito a …", "… KV", títulos pegados.
_ANNOTATION = re.compile(
    r"(?i)\b(?:from|arr|arranged|arrangement|arr\.|edit|edited|ed\.|transcr|transcription|"
    r"transposed|bearb|eingerichtet|harmonized|composed|attribut\w*|atribuid\w*|ascribed|"
    r"alleged|possibly|previously|apologies|kv|bwv|hwv|anh|opus|figaro|waltz|missa|requiem)\b"
    r"|\b(?:K|KV|Op)\s*$"
    # Marcas multilingües de anónimo/tradicional/popular/desconocido y etiquetas de campo.
    r"|anonim|anoniem|anonym|\banon\b|tradicional|traditional|traditionnel|traditioneel"
    r"|tradizionale|traditionell|volksweise|volkslied|popular|populare|unknown|desconocid"
    r"|unbekannt|onbekend|unattributed|compositor|composer|\bauthor\b|\bby\b"
    # Género/marca en cualquier posición + restos de URL ("… hymnary.org …").
    r"|hymn|hymnary|chorale|villancico|himno|motete|madrigal|requiem|waltz|preludio|\bhttp\b"
    r"|\bwww\b|\.org\b|\.com\b"
    # Anotaciones PEGADAS al nombre ("dirharmonized", "Palestrinaed P Wing").
    r"|harmoniz|transcrib|eingericht|bearbeit|arranged|edited"
    r"|[a-zà-ÿ](ed|arr|transcr)\.?\s+[A-Z]"
)
# El nombre TERMINA en un género ("Abbey Hymns", "American Hymn", "Blanche Waltzes").
_GENRE_TAIL = re.compile(
    r"(?i)\b(villancico|cancion|canción|canto|himno|hymn|motete|motet|madrigal|lied|chorale|"
    r"choral|requiem|réquiem|waltz|vals|tango|balada|ballad|preludio|prelude|symphony|sinfonia|"
    r"sonata|canzon|chanson|tune|song|air)s?$"
)
# El nombre TERMINA en un mes ("A Barbon août", "A Barbon mai"): es una fecha, no el nombre.
_MONTH_TAIL = re.compile(
    r"(?i)\b(janvier|février|fevrier|avril|mai|juin|juillet|août|aout|septembre|octobre|"
    r"novembre|décembre|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|"
    r"noviembre|diciembre|gennaio|febbraio|aprile|maggio|giugno|luglio|agosto|settembre|"
    r"ottobre|novembre|dicembre|januar|februar|märz|maerz|dezember)\s*$"
)
# Empieza en minúscula ("anged from Mozart", "ï Felix Mendelssohn"): no es un nombre de autor.
_LOWERCASE_START = re.compile(r"^[a-z]")
# Tonalidad como autor ("A minor", "G major") o pegada al nombre ("A MajorOliver Holden").
_KEY_NAME = re.compile(
    r"(?i)^(?:a|the)?\s*[a-g](?:\s*(?:#|b|♯|♭))?\s*"
    r"(?:major|minor|maj|min|majeure|mineur|mayor|menor|dur|moll)\b"
)
# Tipo de pieza como autor ("A Quick Step", "A Reel", "A Hornpipe", "The Retreat").
_TUNE_TYPE = re.compile(
    r"(?i)^(?:a|an|the)\s+(?:quick\s?step|reel|hornpipe|jig|strathspey|march|waltz|song|tune|"
    r"air|retreat|good(?:\s+one)?|dance|set|medley|piece)\b"
)
# Colecciones y cancioneros como autor ("Aird s Collection", "St. Albans Tune Book").
_COLLECTION = re.compile(
    r"(?i)\b(?:compilation|collection|songbook|tune\s?book|hymn\s?book|repository|anthology|"
    r"selection|psalter|psalmody)s?\b"
)


def _is_annotated(name: str) -> bool:
    text = str(name or "").strip()
    first = text[:1]
    lowercase_unicode = bool(first) and first.isalpha() and not first.isupper()
    return bool(
        _ANNOTATION.search(text)
        or _LOWERCASE_START.match(text)
        or _GENRE_TAIL.search(text)
        or _MONTH_TAIL.search(text)
        or _KEY_NAME.match(text)
        or _TUNE_TYPE.match(text)
        or _COLLECTION.search(text)
        or lowercase_unicode
    )


def _looks_like_person(name: str) -> bool:
    """Nombre plausible: **3+ letras**, sin dígitos, sin rutas ni ':', 1–8 tokens alfabéticos."""
    if _alpha_len(name) < 3:
        return False
    if _is_annotated(name):
        return False
    if any(ch.isdigit() for ch in name) or "/" in name or ":" in name:
        return False
    return bool(_PERSON_LIKE.match(name.strip()))


def _level(row: dict) -> str:
    flags = set(row["flags"])
    # OJO: se evalúa el nombre ORIGINAL; `_parse` ya quita anotaciones y aquí hay que verlas.
    raw = str(row.get("raw") or row["name"] or "")
    if _alpha_len(raw) < 3:
        # Iniciales o fragmentos ("A", "J", "Re"): no son un autor.
        return "not_reviewed_2"
    if _is_annotated(raw):
        # Anotaciones de edición/atribución pegadas al nombre: hay que separarlas.
        return "not_reviewed_2"
    if "anotacion_recortada" in flags:
        # `_parse` tuvo que cortar algo: el nombre guardado no es limpio.
        return "not_reviewed_2"
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
            row["raw"] = person["persons_name"]
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
