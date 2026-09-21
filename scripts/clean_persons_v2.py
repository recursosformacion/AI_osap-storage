"""Limpieza de `persons` v2 — informe por clases (dry-run) y aplicación conservadora.

Aprendizajes de la v1 (revertida): el split por mayúsculas y partir por "and/y/&" rompe
nombres legítimos ("Noah and the Whale", "Peter Paul and Mary" son UNA entidad) y deja años
y anotaciones dentro del nombre. Reglas v2, basadas en los datos reales:

1. **Saneado**: unicode NFKC, sin caracteres de control, espacios colapsados.
2. **Años**: se extraen de `(1685-1750)` o rangos sueltos `1685-1750` → birth/death y se
   **quitan del nombre**.
3. **Etiquetas de rol / anotaciones** (multilingüe, diccionario): se quitan del principio
   (`Composed by:`, `Original Composer:`, `Arranger:`, `Arr:`, `Arreglo:`, `Kompozytor:`,
   `Muzyka:`, `Words:`, `Music:`, `M:`, `T.:`, `after`, `Naar origineel van`, `file ID:`…) y
   se **corta** el nombre al primer segmento de anotación pegado
   (`Arr:`, `arr.`, `Transcribed by`, `Sung by`, `Inspired by`, `harm.`, `Op`, `Collection`…).
4. **Coma**: `Familia, Nombre` es la forma fiable → given/family/sortname.
5. **Sin coma**: family = último token, given = resto, SOLO si 2–4 tokens alfabéticos sin
   dígitos/URLs/etiquetas; si no, se deja vacío y se marca `revisar_split`.
6. **Múltiples**: se parte SOLO por `;`. Los ` and `/` y `/` & ` se marcan
   `revisar_agrupacion` (puede ser grupo o dúo), no se parten automáticamente.
7. **Irrepresentables**: mojibake/CJK/`?` que impide mostrar el nombre → `irrepresentable`
   (se tratan por su obra/MusicXML en la fase siguiente; aquí solo se listan).

    .venv\\Scripts\\python.exe scripts/clean_persons_v2.py             # informe (dry-run)
    .venv\\Scripts\\python.exe scripts/clean_persons_v2.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

_PREFIXES = (
    "composed by", "original composer", "composer", "arranged by", "arranger", "arr",
    "arreglo", "arreglado por", "kompozytor", "aranżacja", "muzyka", "obraz", "words",
    "music", "harm", "harmonized", "transcribed by", "transcription", "sung by",
    "inspired by", "edited by", "after", "naar origineel van", "naar een origineel van",
    "file id", "alt", "mel", "tune", "text", "tekst", "lyrics", "by",
)
_ROLE_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(p) for p in _PREFIXES) + r")\s*[:.\-]?\s*",
    re.IGNORECASE,
)
# Corte en una anotación pegada al nombre (sin separador). Sin `\b` inicial: hay casos
# concatenados ("WondolowskiInspired by", "Wham!arr.") donde no hay frontera de palabra.
_CUT_RE = re.compile(
    r"(?i)(arr:|arr\.|arranged by|arreglo|transcribed by|sung by|inspired by|edited by|"
    r"harm\.|words:|music:|collection of|from premier|from the|based on)"
)
# Tokens de anotación al final del nombre (no son apellidos).
_TRAILING_ANNOT = {
    "op", "opus", "alt", "alt.", "arr", "arr.", "harm", "harm.", "satb", "solo", "trad",
    "anonymous", "anon", "mel", "mel.", "tune", "text", "tekst", "music", "words",
}
_YEARS = re.compile(r"[([]?\s*(\*?)(\d{3,4})\s*[-–—/]\s*[^\d)]{0,3}(\d{3,4})\s*[)\]]?")
_YEAR_ONE = re.compile(r"[([]\s*(\d{3,4})\s*[)\]]")
_TRAILING_YEAR = re.compile(r"[\s,;([]\s*1[0-9]{3}\s*$")
_MOJIBAKE = re.compile(r"[ÃÂÐÑÅ\u0080-\u00ff]{2,}|\?{2,}|[\u3000-\u9fff\u3040-\u30ff]")
_JUNK_CHARS = re.compile(r"[:!*#\"\\|<>\[\]{}~^`]")


def _clean(raw: str) -> str:
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = re.sub(r"[\u0000-\u001f\u007f]", " ", text)
    text = _JUNK_CHARS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" -–—,;.")


def _parse(raw: str) -> dict:
    """Clasifica y normaliza un nombre. No escribe nada."""
    original = str(raw or "")
    flags: list[str] = []
    if _MOJIBAKE.search(original):
        flags.append("irrepresentable")
    text = _clean(original)
    birth = death = None
    m = _YEARS.search(text) or _YEAR_ONE.search(text)
    if m:
        groups = m.groups()
        if len(groups) == 3:
            birth, death = int(groups[1]), int(groups[2])
        else:
            birth = int(groups[0])
        text = (text[: m.start()] + " " + text[m.end() :]).strip()
    text = _ROLE_RE.sub("", text).strip(" :.-")
    cut = _CUT_RE.search(text)
    if cut and cut.start() > 0:
        text = text[: cut.start()].strip(" :.-,")
        flags.append("anotacion_recortada")
    if ";" in text:
        flags.append("multiple")
    if re.search(r"(?i)\s(&|y|and)\s", text):
        flags.append("revisar_agrupacion")
    text = re.sub(r"\s+", " ", text).strip(" -–—,;.")
    # Años sueltos al final ("Martin Luther 1529", "Schein 1628") → se quitan del nombre.
    m_year = _TRAILING_YEAR.search(text)
    if m_year:
        year = int(re.sub(r"\D", "", m_year.group(0)))
        birth = birth or year
        text = text[: m_year.start()].strip(" -–—,;.")
    # Tokens de anotación al final ("Rudolf Friml Op", "… alt", "… satb").
    tokens = text.split()
    while tokens and tokens[-1].lower().strip(".") in _TRAILING_ANNOT:
        tokens.pop()
    text = " ".join(tokens)
    given = family = sort = None
    if text and "," in text:
        fam, _, giv = text.partition(",")
        family, given = fam.strip() or None, giv.strip() or None
        sort = f"{family}, {given}" if family and given else (family or None)
    elif text:
        tokens = text.split()
        plausible = (
            1 <= len(tokens) <= 6
            and all(re.fullmatch(r"[^\W\d_][\w'’.\-]*", t, re.UNICODE) for t in tokens)
        )
        if plausible:
            family, given = tokens[-1], " ".join(tokens[:-1]) or None
            sort = f"{family}, {given}" if given else family
        else:
            flags.append("revisar_split")
    return {
        "raw": original, "name": text, "given": given, "family": family, "sort": sort,
        "birth": birth, "death": death, "flags": flags,
    }


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--show", type=int, default=8, help="muestras por clase")
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
        parsed = [{"id": str(p["persons_id"]), **_parse(p["persons_name"])} for p in people]
        if args.limit:
            parsed = parsed[: args.limit]
        classes: Counter[str] = Counter()
        samples: dict[str, list[str]] = {}
        for row in parsed:
            for flag in row["flags"] or ["ok"]:
                classes[flag] += 1
                samples.setdefault(flag, [])
                if len(samples[flag]) < args.show:
                    samples[flag].append(f"{row['raw'][:58]!r} -> {row['name'][:44]!r}")
        print(f"personas: {len(parsed)}")
        for name, count in classes.most_common():
            print(f"  {name}: {count}")
        for name, _count in classes.most_common():
            print(f"\n--- {name} ---")
            for line in samples.get(name, []):
                print(f"    {line}")
        if not args.apply:
            print("\nDRY-RUN: informe v2. No se escribe nada.")
            return 0
        changed = 0
        with conn.cursor() as cur:
            for row in parsed:
                cur.execute(
                    "UPDATE persons SET persons_name=%s, persons_givenname=%s, "
                    "persons_familyname=%s, persons_sortname=%s, persons_birth_year=%s, "
                    "persons_death_year=%s, persons_updated_at=NOW() WHERE persons_id=%s",
                    (row["name"] or row["raw"], row["given"], row["family"], row["sort"],
                     row["birth"], row["death"], row["id"]),
                )
                changed += cur.rowcount
        print(f"aplicado: {changed}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
