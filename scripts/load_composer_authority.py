#!/usr/bin/env python
"""Cargar autoridad de compositores en osap-storage desde `compositores_wikidata.json`.

Filtra a personas (con viaf_id, nombre de persona), indexa por clave canónica
(`comparison_composer`) SOPORTANDO varios candidatos por clave, y guarda en la BD
(tabla `composer_authority`). Un lookup por "W.A. Mozart" -> clave "wa mozart" ->
candidatos; se prefiere el que tiene viaf_id (identidad fuerte).

Uso:
    python scripts/load_composer_authority.py \
        --source D:/Proyectos/AI_OSAP/osap-compositores/Carga/compositores_wikidata.json \
        --db osap-storage [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

_ANON = {
    "anon", "anon.", "anonymous", "trad", "trad.", "traditional", "attrib.", "attributed",
    "attrib", "unknown", "author unknown", "urheber unbekannt", "urheber unbek.",
}


def composer_key(raw: str) -> str:
    """Clave canónica de compositor (colapsa iniciales/nombres, quita años, unifica anon).
    Self-contained para correr en osap-storage sin depender de osap-api."""
    text = (raw or "").strip()
    if not text:
        return ""
    low = text.lower().replace("'", "").replace("\u2019", "")
    if low in _ANON or low.startswith("urheber unbekannt"):
        return "anonymous"
    text = re.sub(r"\s+\d{3,4}\s*$", "", text)  # años sueltos
    text = re.sub(r"\([^)]*\)", "", text)
    tokens = re.findall(r"[a-z\u00e0-\u00ff]+", low)
    if not tokens:
        return ""
    if len(tokens) > 1 and tokens[-2] == "o":
        surname = "o" + tokens[-1]
        given = tokens[:-2]
    else:
        surname = tokens[-1]
        given = tokens[:-1]
    firsts = "".join(t[0] for t in given)
    return f"{firsts} {surname}".strip()

# Patrones de "obras/páginas" que NO son una persona (se descartan).
_WORK_PATTERNS = re.compile(
    r"Anexo:|Composiciones de|Concierto|Variaciones sobre|Estudios sobre|Recital|"
    r"\([^)]*(Mozart|Bach|Chopin|Beethoven)[^)]*\)|Obra|Sonata|Sinfon|Cuarteto|"
    r"Preelud|Nocturne|Marcha|Danza|Obertura|Réquiem|Oratorio|Mis",
    re.IGNORECASE,
)


def _is_person(entry: dict) -> bool:
    name = (entry.get("nombre") or "").strip()
    if not name or not entry.get("wikidata_id"):
        return False
    return not _WORK_PATTERNS.search(name)


def _clip(value: str | None, n: int) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value[:n] or None


def build(source_path: Path) -> list[dict]:
    data = json.loads(source_path.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("composers", data.get("items", []))
    out: list[dict] = []
    for entry in records:
        if not isinstance(entry, dict) or not _is_person(entry):
            continue
        name = (entry.get("nombre") or "").strip()
        key = composer_key(name)
        if not key:
            continue
        out.append(
            {
                "name": name[:255],
                "key": key,
                "wikidata_id": _clip(entry.get("wikidata_id"), 16),
                "viaf_id": _clip(entry.get("viaf_id"), 32),
                "imslp_id": _clip(entry.get("imslp_id"), 255),
                "birth_date": _clip(entry.get("nacimiento"), 20),
                "death_date": _clip(entry.get("fallecimiento"), 20),
            }
        )
    return out


def stats(source_path: Path) -> None:
    """Estadísticas del JSON antes de tocar la BD."""
    from collections import Counter

    data = json.loads(source_path.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("composers", data.get("items", []))
    n = len(records)
    print(f"=== STATS compositores_wikidata.json ({n} registros) ===")
    cov = {
        "wikidata_id": sum(1 for r in records if r.get("wikidata_id")),
        "viaf_id": sum(1 for r in records if r.get("viaf_id")),
        "imslp_id": sum(1 for r in records if r.get("imslp_id")),
        "nacimiento": sum(1 for r in records if r.get("nacimiento")),
        "fallecimiento": sum(1 for r in records if r.get("fallecimiento")),
    }
    for k, v in cov.items():
        print(f"  con {k:14}: {v:>6} ({100*v/n:.0f}%)")

    persons = [r for r in records if _is_person(r)]
    keys = Counter(composer_key(r["nombre"]) for r in persons)
    multi = sum(1 for k, v in keys.items() if v > 1)
    print(f"  personas con viaf (filtradas): {len(persons)}")
    print(f"  claves canónicas: {len(keys)} | claves con >1 candidato: {multi}")

    print("\n  Resolución (autoridad) de objetivos:")
    for query in ["W.A. Mozart", "Handel", "J. S. Bach", "Frederic Chopin", "Franz Schubert"]:
        k = composer_key(query)
        hits = [r for r in persons if composer_key(r["nombre"]) == k]
        if hits:
            best = max(hits, key=lambda r: 1 if r["viaf_id"] else 0)
            print(f"    {query!r:22} -> {best['nombre']} {best['wikidata_id']} viaf={best['viaf_id']}")
        else:
            print(f"    {query!r:22} -> (no en autoridad)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="ruta a compositores_wikidata.json")
    parser.add_argument("--db", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.stats:
        stats(Path(args.source))
        return 0

    records = build(Path(args.source))
    print(f"{len(records)} compositores (personas con viaf, filtrados)")

    if args.dry_run:
        from collections import Counter

        keys = Counter(r["key"] for r in records)
        multi = sum(1 for k, n in keys.items() if n > 1)
        print(f"claves: {len(keys)} | claves con >1 candidato: {multi}")
        for query in ["J. S. Bach", "Frederic Chopin", "W.A. Mozart"]:
            key = composer_key(query)
            hits = [r for r in records if r["key"] == key]
            if hits:
                best = max(hits, key=lambda r: 1 if r["viaf_id"] else 0)
                print(f"  {query!r} -> {best['name']} {best['wikidata_id']} viaf={best['viaf_id']}")
            else:
                print(f"  {query!r} -> (no en autoridad)")
        return 0

    base = Settings()  # type: ignore[call-arg]
    settings = base.model_copy(update={"db_name": args.db or base.db_name})
    db = Database(settings)

    import asyncio

    async def load():
        async with db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """CREATE TABLE IF NOT EXISTS composer_authority (
                    authority_id  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    wikidata_id   VARCHAR(16),
                    viaf_id       VARCHAR(32),
                    imslp_id      VARCHAR(255),
                    canonical_name VARCHAR(255) NOT NULL,
                    birth_date    VARCHAR(20),
                    death_date    VARCHAR(20),
                    PRIMARY KEY (authority_id),
                    KEY idx_ca_wikidata (wikidata_id),
                    KEY idx_ca_viaf (viaf_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
            )
            await cur.execute(
                """CREATE TABLE IF NOT EXISTS composer_authority_names (
                    authority_id  BIGINT UNSIGNED NOT NULL,
                    name          VARCHAR(255) NOT NULL,
                    normalized_name VARCHAR(128) NOT NULL,
                    source        VARCHAR(32) NOT NULL DEFAULT 'wikidata',
                    KEY idx_can_normalized (normalized_name),
                    KEY idx_can_authority (authority_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
            )
            await cur.execute("DELETE FROM composer_authority_names")
            await cur.execute("DELETE FROM composer_authority")
            for r in records:
                await cur.execute(
                    "INSERT INTO composer_authority (wikidata_id, viaf_id, imslp_id, canonical_name, "
                    "birth_date, death_date) VALUES (%s,%s,%s,%s,%s,%s)",
                    (r["wikidata_id"], r["viaf_id"], r["imslp_id"], r["name"],
                     r["birth_date"], r["death_date"]),
                )
                authority_id = cur.lastrowid
                await cur.execute(
                    "INSERT INTO composer_authority_names (authority_id, name, normalized_name, source) "
                    "VALUES (%s,%s,%s,'wikidata')",
                    (authority_id, r["name"], r["key"]),
                )
            await conn.commit()
        print(f"cargados {len(records)} a composer_authority (+ names) en {settings.db_name}")
        return

    asyncio.run(load())
    return 0


if __name__ == "__main__":
    sys.exit(main())
