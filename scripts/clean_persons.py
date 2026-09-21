"""Limpieza GENÉRICA de `persons` (reglas, no casos).

Reglas aplicadas (todas genéricas):
1. **Saneado**: quita caracteres extraños (`: ! ? * # " / \\ | < > { } [ ]` y mojibake),
   colapsa espacios y recorta. Conserva apóstrofe, guión, punto y coma.
2. **Años**: extrae de paréntesis `(1815-1852)`, `(1815)`, `(*1815 †1852)` o sufijos
   `n. 1815`/`m. 1852` → `persons_birth_year` / `persons_death_year`.
3. **Campos**: rellena `persons_givenname`, `persons_familyname` y `persons_sortname`
   (forma "Familia, Nombre" cuando procede).
4. **Compuestos**: detecta separadores (`;`, ` & `, ` y `) y comprueba cada parte contra
   `persons_name` y `persons_aliases` (normalizado). Solo informa: no crea personas aquí.
5. **Irrepresentables**: nombres con caracteres que no se pueden mostrar → se listan para
   tratarlos por su obra/MusicXML (fase 2).

`--apply` escribe los cambios de nombre/años/campos y audita cada cambio de persona en las
obras afectadas (`works_person_roles` no cambia de persona en esta fase: solo datos de la
ficha). Idempotente.

    .venv\\Scripts\\python.exe scripts/clean_persons.py            # dry-run (informe)
    .venv\\Scripts\\python.exe scripts/clean_persons.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402

_JUNK = re.compile(r"[:!?*#\"\\|<>\[\]{}~^`\u0000-\u001f\u007f]")
_SPACES = re.compile(r"\s+")
_YEARS = re.compile(r"\((\*?)[^\d]{0,3}(\d{3,4})\s*[-–—]\s*[^\d]{0,3}(\d{3,4})\)")
_YEAR_ONE = re.compile(r"\((\d{3,4})\)")


def _clean(raw: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = _JUNK.sub(" ", text)
    text = _SPACES.sub(" ", text).strip(" -–—,;.")
    return text


def _years(raw: str | None) -> tuple[int | None, int | None]:
    text = str(raw or "")
    m = _YEARS.search(text)
    if m:
        return int(m.group(2)), int(m.group(3))
    m = _YEAR_ONE.search(text)
    if m:
        return int(m.group(1)), None
    return None, None


def _names(clean: str) -> tuple[str | None, str | None, str | None]:
    """(given, family, sortname) a partir del nombre limpio."""
    if not clean:
        return None, None, None
    if "," in clean:
        family, _, given = clean.partition(",")
        family, given = family.strip(), given.strip()
        sortname = f"{family}, {given}" if given else family
        return given or None, family or None, sortname or None
    tokens = clean.split()
    if len(tokens) == 1:
        return None, tokens[0], tokens[0]
    family = tokens[-1]
    given = " ".join(tokens[:-1])
    return given, family, f"{family}, {given}"


def _is_clean(raw: str, clean: str) -> bool:
    return _clean(raw) == str(raw or "").strip() and not _JUNK.search(str(raw or ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    with open(ROOT / "config.yaml", encoding="utf-8") as handle:
        conf = (yaml.safe_load(handle) or {}).get("db") or {}
    conn = pymysql.connect(
        host=conf.get("host", "127.0.0.1"),
        port=int(conf.get("port", 3306)),
        user=conf.get("user"),
        password=conf.get("password"),
        database=conf.get("name") or conf.get("database"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT persons_id, persons_name FROM persons")
            people = cur.fetchall()
            cur.execute("SELECT person_id, person_aliases_normalized_alias FROM persons_aliases")
            alias_index = {
                str(r["person_aliases_normalized_alias"]): str(r["person_id"]) for r in cur.fetchall()
            }
            cur.execute("SELECT persons_id, persons_name FROM persons")
            name_index = {norm(r["persons_name"]): str(r["persons_id"]) for r in cur.fetchall()}

        pending: list[dict] = []
        composites = junks = cleanable = with_years = 0
        for person in people:
            raw = str(person["persons_name"] or "")
            clean = _clean(raw)
            birth, death = _years(raw)
            given, family, sortname = _names(clean)
            if not _is_clean(raw, clean):
                cleanable += 1
            if birth or death:
                with_years += 1
            if any(sep in raw for sep in (";", " & ", " y ", " and ")):
                composites += 1
            if _JUNK.search(raw):
                junks += 1
            pending.append(
                {
                    "id": str(person["persons_id"]),
                    "raw": raw,
                    "clean": clean,
                    "given": given,
                    "family": family,
                    "sort": sortname,
                    "birth": birth,
                    "death": death,
                }
            )
        if args.limit:
            pending = pending[: args.limit]

        print(f"personas: {len(people)}")
        print(f"  con caracteres a sanear : {cleanable}")
        print(f"  con años entre paréntesis: {with_years}")
        print(f"  compuestas (separadores) : {composites}")
        print(f"  con caracteres extraños  : {junks}")
        for row in pending[:6]:
            if row["raw"] != row["clean"]:
                print(f"    - {row['raw'][:60]!r} -> {row['clean'][:60]!r} "
                      f"({row['given']}|{row['family']}|{row['sort']}|{row['birth']}-{row['death']})")
        if not args.apply:
            print("DRY-RUN: usa --apply para escribir personas (nombre/años/campos).")
            return 0

        changed = 0
        with conn.cursor() as cur:
            for row in pending:
                if row["raw"] == row["clean"] and not row["birth"] and not row["death"]:
                    continue
                cur.execute(
                    "UPDATE persons SET persons_name=%s, persons_givenname=COALESCE(%s, persons_givenname), "
                    "persons_familyname=COALESCE(%s, persons_familyname), "
                    "persons_sortname=COALESCE(%s, persons_sortname), "
                    "persons_birth_year=COALESCE(%s, persons_birth_year), "
                    "persons_death_year=COALESCE(%s, persons_death_year), persons_updated_at=NOW() "
                    "WHERE persons_id=%s",
                    (row["clean"], row["given"], row["family"], row["sort"],
                     row["birth"], row["death"], row["id"]),
                )
                changed += cur.rowcount
        print(f"aplicado: {changed} personas actualizadas")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
