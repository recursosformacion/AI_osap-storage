"""Informe seco del extractor unificado de metadatos V6 sobre `works`.

Lee una muestra de `works` (solo lectura) y aplica `extract_metadata` al nombre de
origen (`works_song_name`, o `works_title` si falta). Compara título, tonalidad y
atribución con los valores curados y resume acuerdos y marcas.

    .venv\\Scripts\\python.exe scripts/v6_metadata_extract.py --limit 2000
    .venv\\Scripts\\python.exe scripts/v6_metadata_extract.py --origin CPDL --limit 5000
    .venv\\Scripts\\python.exe scripts/v6_metadata_extract.py --only-diff --sample random `
        --out var/v6_metadata_sample.jsonl

No escribe en la base de datos ni modifica títulos: es la base para decidir qué
campos acepta el alta V6 y qué limpieza exige revisión + tabla de correspondencia.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from application.services.instrument_vocabulary import InstrumentVocabulary  # noqa: E402
from application.services.metadata_extractor import Extraction, extract_metadata  # noqa: E402
from domain.services.composer_names import normalize_composer_name  # noqa: E402

_ATTR_MAP = {
    "ANONIMA": "anonymous",
    "ANÓNIMA": "anonymous",
    "TRADICIONAL": "traditional",
    "POPULAR": "traditional",
}
_NORMALIZE = re.compile(r"[^0-9a-záéíóúüñ]+")


def _key(text: str | None) -> str:
    return _NORMALIZE.sub(" ", (text or "").casefold()).strip()


def _key_agrees(extracted: str | None, existing: str) -> bool:
    """El catálogo suele guardar el par relativo (`D major, B minor`)."""
    left, right = _key(extracted), _key(existing)
    return bool(left) and (
        left == right or right.startswith(f"{left} ") or left.startswith(f"{right} ")
    )


def _load_vocabulary(conn: pymysql.Connection) -> InstrumentVocabulary:
    with conn.cursor() as cur:
        cur.execute("SELECT code, name_en, name_es, aliases, imslp_codes FROM instruments")
        rows = cur.fetchall()
    return InstrumentVocabulary.from_rows(rows)


def _load_person_matcher(conn: pymysql.Connection) -> Callable[[str], bool]:
    """Predicado de nombres conocidos para validar créditos ambiguos."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT persons_name AS name FROM persons WHERE persons_name <> '' "
            "UNION SELECT person_aliases_alias FROM persons_aliases "
            "WHERE person_aliases_alias <> ''"
        )
        known = {
            normalize_composer_name(str(row["name"])) for row in cur.fetchall()
        }
    return lambda name: normalize_composer_name(name) in known


def _fetch(conn: pymysql.Connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    where = ["(works_song_name IS NOT NULL AND works_song_name <> '' "
             "OR works_title IS NOT NULL AND works_title <> '')"]
    params: list[Any] = []
    if args.origin:
        where.append("works_origin = %s")
        params.append(args.origin)
    if args.only_diff:
        where.append("COALESCE(works_song_name, '') <> COALESCE(works_title, '')")
    order = "RAND()" if args.sample == "random" else "id"
    sql = (
        "SELECT id, works_title, works_song_name, works_musical_key, works_attr_type "
        "FROM works WHERE " + " AND ".join(f"({item})" for item in where) + f" ORDER BY {order}"
    )
    if args.sample != "random":
        sql += " LIMIT %s OFFSET %s"
        params.extend([args.limit, args.offset])
    else:
        sql += " LIMIT %s"
        params.append(args.limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def _report(rows: list[dict[str, Any]], results: list[Extraction]) -> dict[str, Any]:
    stats: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    title_exact = title_loose = key_seen = key_match = attr_seen = attr_match = 0
    samples: list[dict[str, Any]] = []

    for row, result in zip(rows, results, strict=True):
        curated = str(row["works_title"] or "")
        stats["rows"] += 1
        if result.persons:
            stats["with_persons"] += 1
        if result.attribution:
            stats["with_attribution"] += 1
        if result.key:
            stats["with_key"] += 1
        if result.ensembles:
            stats["with_ensemble"] += 1
        if result.instruments:
            stats["with_instrument"] += 1
        if result.catalogue or result.opus:
            stats["with_catalogue"] += 1
        if result.year or result.year_from:
            stats["with_year"] += 1
        flags.update(result.flags)

        if curated and result.title == curated:
            title_exact += 1
        if curated and _key(result.title) == _key(curated):
            title_loose += 1
        existing_key = str(row["works_musical_key"] or "")
        if result.key and existing_key:
            key_seen += 1
            if _key_agrees(result.key, existing_key):
                key_match += 1
        existing_attr = str(row["works_attr_type"] or "")
        expected = _ATTR_MAP.get(existing_attr.upper())
        if result.attribution and expected:
            attr_seen += 1
            if result.attribution == expected:
                attr_match += 1
        if len(samples) < 15 and curated and _key(result.title) != _key(curated):
            samples.append(
                {
                    "id": row["id"],
                    "curated": curated,
                    "raw": row["works_song_name"],
                    "extracted": result.title,
                    "key": result.key,
                    "persons": [person.name for person in result.persons],
                }
            )

    total = max(stats["rows"], 1)
    return {
        "stats": dict(stats),
        "title_exact_rate": round(title_exact / total, 4),
        "title_loose_rate": round(title_loose / total, 4),
        "key_precision": round(key_match / key_seen, 4) if key_seen else None,
        "key_compared": key_seen,
        "attribution_precision": round(attr_match / attr_seen, 4) if attr_seen else None,
        "attribution_compared": attr_seen,
        "flags": dict(flags.most_common()),
        "title_mismatch_samples": samples,
    }


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--origin", help="IMSLP, PDMX, CPDL…")
    parser.add_argument("--only-diff", action="store_true",
                        help="solo filas donde works_song_name <> works_title")
    parser.add_argument("--sample", choices=("sequential", "random"), default="sequential")
    parser.add_argument("--no-instruments", action="store_true",
                        help="no cargar el vocabulario de instrumentos")
    parser.add_argument("--no-known-persons", action="store_true",
                        help="no validar créditos ambiguos contra el catálogo de personas")
    parser.add_argument("--out", type=Path, help="JSONL con id, texto y extracción")
    parser.add_argument("--seed", type=int, default=20261112)
    args = parser.parse_args()
    random.seed(args.seed)

    with open(ROOT / "config.yaml", encoding="utf-8") as handle:
        conf = (yaml.safe_load(handle) or {}).get("db") or {}
    conn = pymysql.connect(
        host=conf.get("host", "127.0.0.1"), port=int(conf.get("port", 3306)),
        user=conf.get("user"), password=conf.get("password"),
        database=conf.get("name") or conf.get("database"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=True,
    )
    try:
        vocabulary = None if args.no_instruments else _load_vocabulary(conn)
        known_person = None if args.no_known_persons else _load_person_matcher(conn)
        rows = _fetch(conn, args)
    finally:
        conn.close()

    results = [
        extract_metadata(
            row["works_song_name"] or row["works_title"],
            instrument_vocabulary=vocabulary,
            known_person=known_person,
        )
        for row in rows
    ]
    report = _report(rows, results)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as handle:
            for row, result in zip(rows, results, strict=True):
                handle.write(
                    json.dumps(
                        {"id": row["id"], "curated_title": row["works_title"], **result.as_dict()},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        print(f"escrito: {args.out} ({len(results)} filas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
