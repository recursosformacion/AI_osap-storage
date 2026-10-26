"""Enriquece personas incompletas desde Wikidata (SPARQL), sin escribir en la BD.

Estrategia:
1. Si la persona ya tiene `wikidata_qid`, consulta ese QID.
2. Si no, usa identificadores de `persons_identity` (VIAF, ISNI, MusicBrainz, IMSLP,
   GND, RISM) para localizar el QID.
3. `--name-fallback` busca por etiqueta exacta (es/en) y exige humano + compositor;
   solo acepta un candidato único.

Genera propuestas en `data/wikidata_persons/` (JSON + CSV). No modifica `persons`.
La aplicación posterior debe ser una fase separada y revisada.

Uso:
    .venv\\Scripts\\python.exe scripts/wikidata_persons.py --limit 20
    .venv\\Scripts\\python.exe scripts/wikidata_persons.py --limit 100 --name-fallback
    .venv\\Scripts\\python.exe scripts/wikidata_persons.py --person-id <uuid>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "wikidata_persons"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "OSAP-Wikidata-Enricher/1.0 (https://openmusicrepository.com)"
try:
    import certifi

    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = None
BATCH = 30
ID_PROPS = {
    "viaf": "P214",
    "isni": "P213",
    "musicbrainz": "P434",
    "imslp": "P839",
    "gnd": "P227",
    "rism": "P5504",
}
QID = re.compile(r"Q\d+")
YEAR = re.compile(r"([+-]?\d{4})")


def _conf() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
    db = data.get("db") or {}
    if db.get("host") not in {"127.0.0.1", "localhost"}:
        raise SystemExit("rechazado: solo BD local de desarrollo")
    return db


def _db() -> pymysql.connections.Connection:
    conf = _conf()
    return pymysql.connect(
        host=conf.get("host", "127.0.0.1"),
        port=int(conf.get("port", 3306)),
        user=conf.get("user"),
        password=conf.get("password"),
        database=conf.get("name"),
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


def _year(value: Any) -> int | None:
    if value is None:
        return None
    match = YEAR.search(str(value))
    return int(match.group(1)) if match else None


def _qid(value: str | None) -> str | None:
    match = QID.search(value or "")
    return match.group(0) if match else None


def _identifier(value: str | None) -> str:
    text = str(value or "").strip()
    if "/" in text:
        text = text.rstrip("/").rsplit("/", 1)[-1]
    return text


def _sparql(query: str) -> list[dict[str, Any]]:
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
        },
    )
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=90, context=_SSL) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("results", {}).get("bindings", [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(min(2**attempt, 15))
    raise RuntimeError(f"SPARQL falló: {last_error}")


def _select_persons(limit: int, offset: int, person_id: str | None) -> list[dict[str, Any]]:
    where = [
        "p.persons_status = 'active'",
        "p.persons_visible = 1",
        "p.persons_type = 'person'",
        "(p.persons_birth_year IS NULL OR p.persons_death_year IS NULL "
        "OR p.persons_nationality IS NULL OR p.persons_biography_summary IS NULL)",
    ]
    params: list[Any] = []
    if person_id:
        where = ["p.persons_id = %s"]
        params.append(person_id)
    sql = (
        "SELECT p.persons_id, p.persons_name, p.persons_birth_year, p.persons_death_year, "
        "p.persons_nationality, p.persons_biography_summary "
        "FROM persons p WHERE " + " AND ".join(where) + " ORDER BY p.persons_id"
    )
    if limit:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with _db() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def _identities(person_ids: list[str]) -> dict[str, list[dict[str, str]]]:
    if not person_ids:
        return {}
    out: dict[str, list[dict[str, str]]] = {}
    with _db() as conn, conn.cursor() as cur:
        for start in range(0, len(person_ids), 1000):
            chunk = person_ids[start : start + 1000]
            placeholders = ",".join(["%s"] * len(chunk))
            cur.execute(
                "SELECT persons_id, identity_type, identity_value FROM persons_identity "
                f"WHERE persons_id IN ({placeholders})",
                chunk,
            )
            for row in cur.fetchall():
                out.setdefault(row["persons_id"], []).append(row)
    return out


def _query_qids(qids: list[str]) -> dict[str, dict[str, Any]]:
    values = " ".join(f"wd:{qid}" for qid in qids)
    rows = _sparql(_fields_query(f"VALUES ?person {{ {values} }}"))
    return _group_rows(rows)


def _query_ids(prop: str, values: list[str]) -> dict[str, dict[str, Any]]:
    values_sql = " ".join(json.dumps(v) for v in values)
    clause = f"VALUES ?id {{ {values_sql} }} ?person wdt:{prop} ?id ."
    rows = _sparql(_fields_query(clause, include_id=True))
    return _group_rows(rows, include_id=True)


def _fields_query(clause: str, include_id: bool = False) -> str:
    id_select = " ?id" if include_id else ""
    return f"""
SELECT ?person ?personLabel ?birth ?death ?nationalityLabel ?description ?image{id_select}
       ?isni ?viaf ?musicbrainz ?imslp ?gnd ?rism WHERE {{
  {clause}
  OPTIONAL {{ ?person wdt:P569 ?birth. }}
  OPTIONAL {{ ?person wdt:P570 ?death. }}
  OPTIONAL {{
    ?person wdt:P27 ?nationality.
    ?nationality rdfs:label ?nationalityLabel.
    FILTER(lang(?nationalityLabel) = "es")
  }}
  OPTIONAL {{
    ?person schema:description ?description.
    FILTER(lang(?description) = "es")
  }}
  OPTIONAL {{ ?person wdt:P18 ?image. }}
  OPTIONAL {{ ?person wdt:P213 ?isni. }}
  OPTIONAL {{ ?person wdt:P214 ?viaf. }}
  OPTIONAL {{ ?person wdt:P434 ?musicbrainz. }}
  OPTIONAL {{ ?person wdt:P839 ?imslp. }}
  OPTIONAL {{ ?person wdt:P227 ?gnd. }}
  OPTIONAL {{ ?person wdt:P5504 ?rism. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
}}"""


def _group_rows(rows: list[dict[str, Any]], include_id: bool = False) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        qid = _qid((row.get("person") or {}).get("value"))
        if not qid:
            continue
        item = out.setdefault(qid, {"qid": qid, "_ids": set(), "labels": set()})
        if include_id:
            value = (row.get("id") or {}).get("value")
            if value:
                item["_ids"].add(str(value))
        if row.get("personLabel"):
            item["labels"].add((row["personLabel"] or {}).get("value"))
        if row.get("birth") and not item.get("birth_year"):
            item["birth_year"] = _year((row["birth"] or {}).get("value"))
        if row.get("death") and not item.get("death_year"):
            item["death_year"] = _year((row["death"] or {}).get("value"))
        if row.get("nationalityLabel") and not item.get("nationality"):
            item["nationality"] = (row["nationalityLabel"] or {}).get("value")
        if row.get("description") and not item.get("description"):
            item["description"] = (row["description"] or {}).get("value")
        if row.get("image") and not item.get("image"):
            item["image"] = (row["image"] or {}).get("value")
        for key in ("isni", "viaf", "musicbrainz", "imslp", "gnd", "rism"):
            if row.get(key):
                item.setdefault("identifiers", []).append(
                    {"type": key, "value": (row[key] or {}).get("value")}
                )
    for item in out.values():
        if item.get("image") and "/Special:FilePath/" in item["image"]:
            item["image"] = item["image"].split("/Special:FilePath/")[-1]
        item["labels"] = sorted(label for label in item["labels"] if label)
        item["_ids"] = sorted(item["_ids"])
    return out


def _name_matches(names: list[str]) -> dict[str, dict[str, Any]]:
    values = " ".join(
        f"{json.dumps(name)}@{lang}" for name in names for lang in ("es", "en")
    )
    query = f"""
SELECT ?person ?name ?personLabel ?birth ?death ?nationalityLabel ?description ?image
       ?isni ?viaf ?musicbrainz ?imslp ?gnd ?rism WHERE {{
  VALUES ?name {{ {values} }}
  ?person rdfs:label ?name; wdt:P31 wd:Q5.
  FILTER EXISTS {{ ?person wdt:P106 wd:Q36834. }}
  OPTIONAL {{ ?person wdt:P569 ?birth. }}
  OPTIONAL {{ ?person wdt:P570 ?death. }}
  OPTIONAL {{
    ?person wdt:P27 ?nationality.
    ?nationality rdfs:label ?nationalityLabel.
    FILTER(lang(?nationalityLabel) = "es")
  }}
  OPTIONAL {{
    ?person schema:description ?description.
    FILTER(lang(?description) = "es")
  }}
  OPTIONAL {{ ?person wdt:P18 ?image. }}
  OPTIONAL {{ ?person wdt:P213 ?isni. }}
  OPTIONAL {{ ?person wdt:P214 ?viaf. }}
  OPTIONAL {{ ?person wdt:P434 ?musicbrainz. }}
  OPTIONAL {{ ?person wdt:P839 ?imslp. }}
  OPTIONAL {{ ?person wdt:P227 ?gnd. }}
  OPTIONAL {{ ?person wdt:P5504 ?rism. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
}}"""
    rows = _sparql(query)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        qid = _qid((row.get("person") or {}).get("value"))
        if not qid:
            continue
        item = out.setdefault(qid, {"qid": qid, "names": set(), "labels": set()})
        if row.get("name"):
            item["names"].add((row["name"] or {}).get("value"))
        if row.get("personLabel"):
            item["labels"].add((row["personLabel"] or {}).get("value"))
        if row.get("birth") and not item.get("birth_year"):
            item["birth_year"] = _year((row["birth"] or {}).get("value"))
        if row.get("death") and not item.get("death_year"):
            item["death_year"] = _year((row["death"] or {}).get("value"))
        if row.get("nationalityLabel") and not item.get("nationality"):
            item["nationality"] = (row["nationalityLabel"] or {}).get("value")
        if row.get("description") and not item.get("description"):
            item["description"] = (row["description"] or {}).get("value")
        if row.get("image") and not item.get("image"):
            item["image"] = (row["image"] or {}).get("value")
    for item in out.values():
        item["names"] = sorted(item["names"])
        item["labels"] = sorted(item["labels"])
    return out


def _proposals(persons: list[dict[str, Any]], name_fallback: bool) -> list[dict[str, Any]]:
    ids = [p["persons_id"] for p in persons]
    identity = _identities(ids)
    result: dict[str, dict[str, Any]] = {}

    qid_people: dict[str, list[str]] = {}
    id_people: dict[str, list[str]] = {}
    no_match: list[str] = []
    for person in persons:
        pid = person["persons_id"]
        found_qid = None
        for row in identity.get(pid, []):
            if (row.get("identity_type") or "").lower() == "wikidata_qid":
                found_qid = _qid(row.get("identity_value"))
                if found_qid:
                    break
        if found_qid:
            qid_people.setdefault(found_qid, []).append(pid)
            continue
        used = False
        for row in identity.get(pid, []):
            kind = (row.get("identity_type") or "").lower()
            if kind in ID_PROPS:
                value = _identifier(row.get("identity_value"))
                if value:
                    id_people.setdefault(f"{ID_PROPS[kind]}\0{value}", []).append(pid)
                    used = True
        if not used:
            no_match.append(pid)

    qids = list(qid_people)
    for start in range(0, len(qids), BATCH):
        chunk = qids[start : start + BATCH]
        found = _query_qids(chunk)
        for qid in chunk:
            data = found.get(qid)
            if data:
                for pid in qid_people[qid]:
                    result[pid] = {"match_method": "wikidata_qid", "confidence": 0.99, **data}
            else:
                no_match.extend(qid_people[qid])

    by_prop: dict[str, list[tuple[str, str]]] = {}
    for composite, pids in id_people.items():
        prop, value = composite.split("\0", 1)
        by_prop.setdefault(prop, []).append((value, pids[0]))
    for prop, entries in by_prop.items():
        for start in range(0, len(entries), BATCH):
            chunk = entries[start : start + BATCH]
            found = _query_ids(prop, [value for value, _ in chunk])
            reverse = {value: pid for value, pid in chunk}
            for _match_qid, data in found.items():
                matched_ids = set(data.get("_ids") or [])
                for value in matched_ids:
                    pid = reverse.get(value)
                    if pid and pid not in result:
                        result[pid] = {
                            "match_method": f"identifier:{prop}",
                            "confidence": 0.95,
                            **data,
                        }

    if name_fallback:
        unresolved = [p for p in persons if p["persons_id"] not in result]
        for start in range(0, len(unresolved), BATCH):
            chunk = unresolved[start : start + BATCH]
            candidates = _name_matches([str(p["persons_name"]) for p in chunk])
            for person in chunk:
                pid = person["persons_id"]
                name = str(person["persons_name"]).strip().casefold()
                matches = [
                    data
                    for data in candidates.values()
                    if name in {n.casefold() for n in data.get("names", [])}
                ]
                if len(matches) == 1:
                    result[pid] = {"match_method": "name_exact", "confidence": 0.70, **matches[0]}
                elif len(matches) > 1:
                    result[pid] = {
                        "match_method": "ambiguous_name",
                        "confidence": 0.0,
                        "candidates": [m["qid"] for m in matches],
                    }

    out: list[dict[str, Any]] = []
    for person in persons:
        data = result.get(person["persons_id"], {})
        out.append(
            {
                "persons_id": person["persons_id"],
                "persons_name": person["persons_name"],
                "current": {
                    "birth_year": person.get("persons_birth_year"),
                    "death_year": person.get("persons_death_year"),
                    "nationality": person.get("persons_nationality"),
                    "summary": person.get("persons_biography_summary"),
                },
                "match_method": data.get("match_method"),
                "confidence": data.get("confidence", 0.0),
                "qid": data.get("qid"),
                "wikidata_label": (data.get("labels") or [None])[0],
                "birth_year": data.get("birth_year"),
                "death_year": data.get("death_year"),
                "nationality": data.get("nationality"),
                "description": data.get("description"),
                "image": data.get("image"),
                "identifiers": data.get("identifiers", []),
                "candidates": data.get("candidates", []),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--person-id", default=None)
    ap.add_argument("--name-fallback", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    persons = _select_persons(args.limit, args.offset, args.person_id)
    if not persons:
        print("No hay personas candidatas.")
        return 0
    proposals = _proposals(persons, args.name_fallback)
    stamp = date.today().strftime("%Y%m%d")
    out_dir = args.out.parent if args.out else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out or (out_dir / f"proposals_{stamp}.json")
    csv_path = json_path.with_suffix(".csv")
    json_path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "persons_id", "persons_name", "match_method", "confidence", "qid",
                "wikidata_label", "birth_year", "death_year", "nationality",
                "description", "image",
            ],
        )
        writer.writeheader()
        for row in proposals:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})
    matched = sum(1 for row in proposals if row.get("qid"))
    print(f"personas={len(proposals)} con_qid={matched} sin_match={len(proposals) - matched}")
    print(f"json={json_path}")
    print(f"csv={csv_path}")
    print("No se ha escrito en la BD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())







