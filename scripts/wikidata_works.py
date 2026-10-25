"""Propone metadatos de obras desde Wikidata, sin escribir en la BD.

Solo usa obras cuyo compositor ya tiene un `wikidata_qid`; busca por el par
(compositor QID, título exacto es/en). No hace búsquedas por nombre de obra suelto.
Las coincidencias múltiples quedan como ambiguas.

Genera propuestas en `data/wikidata_works/` (JSON + CSV). No modifica `works`.

Uso:
    .venv\\Scripts\\python.exe scripts/wikidata_works.py --limit 20
    .venv\\Scripts\\python.exe scripts/wikidata_works.py --limit 100 --out data/wikidata_works/lote.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from wikidata_persons import _db, _qid, _sparql, _year  # noqa: E402

OUT_DIR = ROOT / "data" / "wikidata_works"
BATCH = 30


def _select(limit: int, offset: int) -> list[dict[str, Any]]:
    sql = """
        SELECT w.id, w.works_title, w.works_song_name, w.works_year,
               w.works_catalogue, w.works_description,
               p.persons_id, p.persons_name, i.identity_value AS qid
        FROM works w
        JOIN works_person_roles r
          ON r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1
        JOIN persons p ON p.persons_id = r.works_person_roles_person_id
        JOIN persons_identity i
          ON i.persons_id = p.persons_id AND i.identity_type = 'wikidata_qid'
        WHERE (w.works_description IS NULL OR w.works_description = ''
               OR w.works_year IS NULL OR w.works_catalogue IS NULL)
          AND i.identity_value LIKE 'Q%%'
        GROUP BY w.id, w.works_title, w.works_song_name, w.works_year,
                 w.works_catalogue, w.works_description,
                 p.persons_id, p.persons_name, i.identity_value
        ORDER BY w.id
    """
    params: list[Any] = []
    if limit:
        sql += " LIMIT %s OFFSET %s"
        params = [limit, offset]
    with _db() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def _query(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for row in rows:
        qid = _qid(row.get("qid"))
        title = str(row.get("works_title") or "").strip()
        if not qid or not title:
            continue
        for lang in ("es", "en"):
            values.append(f"(wd:{qid} {json.dumps(title)}@{lang})")
    if not values:
        return []
    query = f"""
SELECT ?work ?workLabel ?composer ?composerLabel ?title ?date ?catalogue
       ?genreLabel ?languageLabel ?duration ?instrumentationLabel ?description ?mbid WHERE {{
  VALUES (?composer ?title) {{ {' '.join(values)} }}
  ?work wdt:P86 ?composer; rdfs:label ?title.
  OPTIONAL {{ ?work wdt:P577 ?date. }}
  OPTIONAL {{ ?work wdt:P528 ?catalogue. }}
  OPTIONAL {{
    ?work wdt:P136 ?genre.
    ?genre rdfs:label ?genreLabel.
    FILTER(lang(?genreLabel) = "es")
  }}
  OPTIONAL {{
    ?work wdt:P407 ?language.
    ?language rdfs:label ?languageLabel.
    FILTER(lang(?languageLabel) = "es")
  }}
  OPTIONAL {{ ?work wdt:P2047 ?duration. }}
  OPTIONAL {{
    ?work wdt:P870 ?instrumentation.
    ?instrumentation rdfs:label ?instrumentationLabel.
    FILTER(lang(?instrumentationLabel) = "es")
  }}
  OPTIONAL {{
    ?work schema:description ?description.
    FILTER(lang(?description) = "es")
  }}
  OPTIONAL {{ ?work wdt:P435 ?mbid. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
}}"""
    return _sparql(query)


def _proposals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = _query(rows)
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        qid = _qid((candidate.get("composer") or {}).get("value"))
        title = (candidate.get("title") or {}).get("value")
        if qid and title:
            by_key.setdefault((qid, title.casefold()), []).append(candidate)

    out: list[dict[str, Any]] = []
    for row in rows:
        qid = _qid(row.get("qid"))
        titles = {str(row.get("works_title") or "").strip().casefold()}
        if row.get("works_song_name"):
            titles.add(str(row["works_song_name"]).strip().casefold())
        found: list[dict[str, Any]] = []
        for title in titles:
            found.extend(by_key.get((qid, title), []))
        unique = {((c.get("work") or {}).get("value")): c for c in found if c.get("work")}
        if len(unique) == 1:
            candidate = next(iter(unique.values()))
            work = candidate.get("work") or {}
            out.append(
                {
                    "works_id": row["id"],
                    "current_title": row["works_title"],
                    "composer": row.get("persons_name"),
                    "composer_qid": qid,
                    "match_method": "composer_qid+title",
                    "confidence": 0.80,
                    "qid": _qid(work.get("value")),
                    "wikidata_label": (candidate.get("workLabel") or {}).get("value"),
                    "year": _year((candidate.get("date") or {}).get("value")),
                    "catalogue": (candidate.get("catalogue") or {}).get("value"),
                    "genre": (candidate.get("genreLabel") or {}).get("value"),
                    "language": (candidate.get("languageLabel") or {}).get("value"),
                    "duration": (candidate.get("duration") or {}).get("value"),
                    "instrumentation": (candidate.get("instrumentationLabel") or {}).get("value"),
                    "description": (candidate.get("description") or {}).get("value"),
                    "musicbrainz_work_id": (candidate.get("mbid") or {}).get("value"),
                }
            )
        elif len(unique) > 1:
            out.append(
                {
                    "works_id": row["id"],
                    "current_title": row["works_title"],
                    "composer": row.get("persons_name"),
                    "composer_qid": qid,
                    "match_method": "ambiguous",
                    "confidence": 0.0,
                    "candidates": sorted(unique),
                }
            )
        else:
            out.append(
                {
                    "works_id": row["id"],
                    "current_title": row["works_title"],
                    "composer": row.get("persons_name"),
                    "composer_qid": qid,
                    "match_method": "no_match",
                    "confidence": 0.0,
                }
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rows = _select(args.limit, args.offset)
    if not rows:
        print("No hay obras candidatas con compositor QID.")
        return 0
    proposals = _proposals(rows)
    stamp = date.today().strftime("%Y%m%d")
    out_dir = args.out.parent if args.out else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out or (out_dir / f"proposals_{stamp}.json")
    csv_path = json_path.with_suffix(".csv")
    json_path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        fields = ["works_id", "current_title", "composer", "match_method", "confidence",
                  "qid", "wikidata_label", "year", "catalogue", "genre", "language",
                  "duration", "instrumentation", "description", "musicbrainz_work_id"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in proposals:
            writer.writerow({key: row.get(key) for key in fields})
    matched = sum(1 for row in proposals if row.get("qid"))
    print(f"obras={len(proposals)} con_qid={matched} sin_match={len(proposals) - matched}")
    print(f"json={json_path}")
    print(f"csv={csv_path}")
    print("No se ha escrito en la BD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

