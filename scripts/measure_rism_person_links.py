"""Medición read-only: enlazar la persona RISM de las 82 aceptadas con nuestra `persons`.

Jerarquía: GND → VIAF → (otros ids enlazados) → nombre/variantes (respaldo, NO auto).
Clasificación: enlazada_<tipo> / ambigua / sin_identidad. No escribe nada.

    .venv\\Scripts\\python.exe scripts/measure_rism_person_links.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402

ID_TYPES = ("gnd", "viaf", "wikidata_qid", "imslp", "isni", "musicbrainz", "discogs")
ID_TYPES_ORDER = ("gnd", "viaf", "wikidata_qid", "imslp", "isni")


def _key(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().lower()
    match = re.search(r"(\d{4,})$", text)
    return match.group(1) if match else text


def _matchkey(name: str | None) -> str:
    return " ".join(sorted(norm(name).split()))


def _load_accepted(decisions_path: Path) -> list[dict]:
    with open(decisions_path, encoding="utf-8") as fh:
        return [
            r for r in csv.DictReader(fh)
            if r["decision"] == "accept" and not r["our_person_id"]
        ]


def link_rows(conn, decisions_path: Path) -> list[dict]:
    """Por cada obra aceptada sin persona: work_id, rism_person_id, categoría y persons_id."""
    accepted = _load_accepted(decisions_path)
    with conn.cursor() as cur:
        cur.execute("SELECT rism_person_id, COALESCE(rism_canonical_id, rism_person_id) canon, "
                    "       rism_gnd, rism_viaf FROM rism_persons")
        canon_of: dict[str, str] = {}
        ids: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"gnd": set(), "viaf": set()})
        for r in cur.fetchall():
            canon_of[r["rism_person_id"]] = r["canon"]
            if r["rism_gnd"]:
                ids[r["canon"]]["gnd"].add(_key(r["rism_gnd"]))
            if r["rism_viaf"]:
                ids[r["canon"]]["viaf"].add(_key(r["rism_viaf"]))

        cur.execute("SELECT persons_id, identity_type, identity_value FROM persons_identity "
                    "WHERE persons_id IS NOT NULL")
        ours: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for r in cur.fetchall():
            type_ = (r["identity_type"] or "").lower()
            if type_ in ID_TYPES:
                ours[type_][_key(r["identity_value"])].add(r["persons_id"])

        cur.execute("SELECT persons_id, persons_name FROM persons")
        our_names: dict[str, set[str]] = defaultdict(set)
        for r in cur.fetchall():
            our_names[_matchkey(r["persons_name"])].add(r["persons_id"])
        cur.execute("SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases")
        for r in cur.fetchall():
            if r["a"]:
                our_names[_matchkey(r["a"])].add(r["person_id"])

    cache: dict[str, dict] = {}
    for rism_id, works in _group_by_person(accepted).items():
        canon = canon_of.get(rism_id, rism_id)
        groups = ids.get(canon, {"gnd": set(), "viaf": set()})
        category, person_id = "sin_identidad", None
        for type_ in ID_TYPES_ORDER:
            values = groups.get(type_)
            if not values:
                continue
            found: set[str] = set()
            for value in values:
                found |= ours.get(type_, {}).get(value, set())
            if len(found) == 1:
                category, person_id = f"enlazada_{type_}", next(iter(found))
                break
            if len(found) > 1:
                category = "ambigua"
                break
        if person_id is None and category == "sin_identidad":
            found = our_names.get(_matchkey(works[0]["rism_name"]), set())
            if len(found) == 1:
                category, person_id = "enlazada_nombre", next(iter(found))
            elif len(found) > 1:
                category = "ambigua"
        cache[rism_id] = {"category": category, "person_id": person_id,
                          "name": works[0]["rism_name"]}

    rows = []
    for row in accepted:
        info = cache[row["rism_person_id"]]
        rows.append({
            "work_id": int(row["work_id"]), "title_key": row["title_key"],
            "rism_person_id": row["rism_person_id"], "rism_name": row["rism_name"],
            "category": info["category"], "our_person_id": info["person_id"],
        })
    return rows


def _group_by_person(accepted: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in accepted:
        grouped[row["rism_person_id"]].append(row)
    return grouped


def run(decisions_path: Path, out_path: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    rows = link_rows(conn, decisions_path)
    conn.close()

    counts = Counter(r["category"] for r in rows)
    by_person: dict[str, dict] = {}
    for r in rows:
        by_person.setdefault(r["rism_person_id"], {"category": r["category"],
                                                   "person_id": r["our_person_id"],
                                                   "name": r["rism_name"], "works": 0})
        by_person[r["rism_person_id"]]["works"] += 1

    lines = [
        "# Enlace RISM person → `persons` (82 aceptadas, read-only)\n",
        f"- Personas RISM distintas: **{len(by_person)}** | obras: **{len(rows)}**\n",
        "## Por obra\n",
        "| Resultado | Obras |",
        "|---|---|",
    ]
    for k, v in counts.most_common():
        lines.append(f"| {k} | {v} |")
    lines.append("\n## Detalle por persona RISM\n")
    lines.append("| rism_person | nombre | categoría | persons_id | obras |")
    lines.append("|---|---|---|---|---|")
    for rism_id, r in sorted(by_person.items(), key=lambda kv: kv[1]["category"]):
        lines.append(f"| {rism_id} | {r['name']} | {r['category']} | {r['person_id'] or '—'} | {r['works']} |")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("obras:", len(rows), "personas:", len(by_person), "por obra:", dict(counts))
    print("informe:", out_path)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--decisions", type=Path, default=Path(r"G:\rism\rism_decisions.csv"))
    ap.add_argument("--out", type=Path, default=ROOT / "docsNew" / "rism-enlace-82.md")
    args = ap.parse_args()
    run(args.decisions, args.out)


if __name__ == "__main__":
    main()
