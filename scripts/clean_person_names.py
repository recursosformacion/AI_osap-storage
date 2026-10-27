"""Propone limpiar nombres de personas contaminados con titulos, URLs o creditos.

No modifica la BD. Detecta nombres con hymnary/vwml/musescore/youtube/imslp y extrae:
- credito explicito "Composed by ...";
- titulo de obra desde la URL/slug;
- nombre limpio quitando URLs y segmentos que coinciden con el titulo de una obra asociada.
Los casos sin compositor recuperable quedan como `work_title` o `invalid`.

Uso:
    .venv\\Scripts\\python.exe scripts/clean_person_names.py
    .venv\\Scripts\\python.exe scripts/clean_person_names.py --apply  # futuro, no implementado
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "person_name_cleanup"
MARKERS = ("www.", "http", "hymnary", "vwml", "musescore", "youtube", "patreon", "imslp")
URL_RE = re.compile(r"(?i)(?:https?\s*//|www\.)\S+")
CREDIT_RE = re.compile(
    r"(?i)composed\s+by\s+(.+?)(?=\s*(?:piano\s+arrangement|arrangement|arranged|performed|transcribed|full|if\s+you\s+want|source|chords\s+by|based\s+on|https?|www\.|$))"
)
HYMNARY_RE = re.compile(r"(?i)hymnary\.org/+?(?:text|hymn)/([^?#\s]+)")
IMSLP_RE = re.compile(r"(?i)imslp\.org/wiki/([^?#\s)]+)")
SEPARATOR_RE = re.compile(r"\s+[-–—]\s+")


def _db() -> pymysql.connections.Connection:
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    return pymysql.connect(
        host=conf["host"],
        port=conf["port"],
        user=conf["user"],
        password=conf["password"],
        database=conf["name"],
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _slug_title(value: str) -> str:
    text = value.replace("_", " ").replace("+", " ")
    return re.sub(r"\s+", " ", text).strip(" .-")


def _clean(name: str) -> str:
    text = URL_RE.sub(" ", name)
    text = re.sub(
        r"(?i)\b(?:source|transcribed|arranged|performed|full playthrough|if you want to donate|please check out)\b.*$",
        " ",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return text


def _propose(name: str, work_titles: list[str]) -> dict[str, Any]:
    url_title = None
    m = HYMNARY_RE.search(name)
    if m:
        url_title = _slug_title(m.group(1))
    m = IMSLP_RE.search(name)
    if m:
        url_title = _slug_title(m.group(1).replace("_", " "))
    credit = CREDIT_RE.search(name)
    if credit:
        candidate = _clean(credit.group(1)).strip(" .,-")
        if candidate:
            return {
                "kind": "composer_name",
                "candidate_name": candidate,
                "evidence": credit.group(0),
                "confidence": 0.9,
                "url_title": url_title,
            }
    if url_title or "hymnary" in name.casefold() or "vwml" in name.casefold():
        target = work_titles[0] if work_titles else (url_title or name)
        parts = [part.strip(" .,-") for part in SEPARATOR_RE.split(target) if part.strip(" .,-")]
        if len(parts) >= 2 and not any(marker in parts[-1].casefold() for marker in MARKERS):
            words = parts[-1].split()
            if 1 < len(words) <= 6:
                return {
                    "kind": "composer_from_work_title",
                    "candidate_name": parts[-1],
                    "work_title": " - ".join(parts[:-1]),
                    "evidence": target,
                    "confidence": 0.55,
                    "url_title": url_title,
                }
        return {
            "kind": "work_title",
            "candidate_name": target,
            "evidence": name,
            "confidence": 0.6 if work_titles else 0.45,
            "url_title": url_title,
        }
    cleaned = _clean(name)
    segments = [s.strip(" .,-") for s in SEPARATOR_RE.split(cleaned) if s.strip(" .,-")]
    work_norms = {_norm(t) for t in work_titles if t}
    kept = [s for s in segments if _norm(s) not in work_norms]
    candidate = " ".join(kept).strip()
    if candidate and not any(marker in candidate.casefold() for marker in MARKERS) and not re.search(r"(?i)transcrib|arrang|improvis|chords|performed|based on", name):
        # Evitar metros/tune names y cadenas de creditos.
        words = candidate.split()
        if 1 < len(words) <= 7 and len(candidate) <= 80:
            return {
                "kind": "composer_name",
                "candidate_name": candidate,
                "evidence": cleaned,
                "confidence": 0.65,
                "url_title": url_title,
            }
    if url_title:
        return {
            "kind": "work_title",
            "candidate_name": url_title,
            "evidence": name,
            "confidence": 0.5,
            "url_title": url_title,
        }
    return {"kind": "invalid", "candidate_name": None, "evidence": name, "confidence": 0.0, "url_title": url_title}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "proposals.json")
    args = ap.parse_args()
    conn = _db()
    try:
        with conn.cursor() as cur:
            where = " OR ".join(["p.persons_name LIKE %s"] * len(MARKERS))
            cur.execute(
                "SELECT p.persons_id, p.persons_name, GROUP_CONCAT(DISTINCT w.works_title SEPARATOR ' || ') AS titles "
                "FROM persons p LEFT JOIN works_person_roles r ON r.works_person_roles_person_id=p.persons_id "
                "AND r.works_person_roles_role_id=1 LEFT JOIN works w ON w.id=r.works_person_roles_work_id "
                f"WHERE {where} GROUP BY p.persons_id, p.persons_name LIMIT 1000",
                [f"%{m}%" for m in MARKERS],
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    proposals: list[dict[str, Any]] = []
    for row in rows:
        titles = [t.strip() for t in (row.get("titles") or "").split(" || ") if t.strip()]
        proposal = _propose(str(row["persons_name"]), titles)
        proposals.append(
            {
                "persons_id": row["persons_id"],
                "persons_name": row["persons_name"],
                "works": titles,
                **proposal,
            }
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = args.out.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["persons_id", "persons_name", "works", "kind", "candidate_name", "confidence", "evidence"]
        )
        writer.writeheader()
        for row in proposals:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})
    from collections import Counter

    print(Counter(row["kind"] for row in proposals))
    print(f"json={args.out}")
    print(f"csv={csv_path}")
    print("No se ha escrito en la BD.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

