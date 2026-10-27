"""Resuelve conflictos de limpieza de nombres fusionando solo con evidencia de autoridad.

Lee `data/person_name_cleanup/ai_validation.json`, busca la persona candidata que ya existe y
comprueba si coincide mediante MBID (validación MB), VIAF, GND o Wikidata. No fusiona por
nombre solo. Por defecto es dry-run; `--apply` mueve obras/identificadores y marca la persona
falsa como merged.

Uso:
    .venv\\Scripts\\python.exe scripts/resolve_cleanup_conflicts.py
    .venv\\Scripts\\python.exe scripts/resolve_cleanup_conflicts.py --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pymysql
import yaml

ROOT = Path(__file__).resolve().parent.parent
CLEANUP = ROOT / "data" / "person_name_cleanup"
DECISIONS = CLEANUP / "ai_validation.json"
MB = CLEANUP / "mb_validation.json"
CACHE_PATH = CLEANUP / "authority_cache.json"
REPORT = ROOT / "data" / "cleanup_conflicts_report.csv"
try:
    import certifi

    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = None
_cache: dict[str, Any] = {}
if CACHE_PATH.exists():
    try:
        _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _cache = {}


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _get_json(url: str) -> Any:
    if url in _cache:
        return _cache[url]
    request = urllib.request.Request(
        url, headers={"User-Agent": "OSAP-Authority-Resolver/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30, context=_SSL) as response:
        payload = json.loads(response.read().decode("utf-8"))
    _cache[url] = payload
    return payload


def _save_cache() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")


def _viaf(name: str) -> list[dict[str, Any]]:
    url = "https://viaf.org/viaf/AutoSuggest?" + urllib.parse.urlencode({"query": name})
    try:
        payload = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []
    return [r for r in (payload.get("result") or []) if str(r.get("nametype", "")).lower() == "personal"]


def _gnd(name: str) -> list[dict[str, Any]]:
    url = "https://lobid.org/gnd/search?" + urllib.parse.urlencode({"q": name, "format": "json", "size": 5})
    try:
        payload = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []
    return list(payload.get("member") or [])


def _wikidata(name: str) -> list[dict[str, Any]]:
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbsearchentities", "search": name, "language": "en", "format": "json", "limit": 5}
    )
    try:
        payload = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []
    return list(payload.get("search") or [])


def _identities(cur, person_id: str) -> set[tuple[str, str]]:
    cur.execute("SELECT identity_type, identity_value FROM persons_identity WHERE persons_id=%s", (person_id,))
    return {(str(r["identity_type"]).lower(), str(r["identity_value"])) for r in cur.fetchall()}


def _existing(cur, name: str) -> list[dict[str, Any]]:
    cur.execute(
        "SELECT persons_id, persons_name, persons_status FROM persons "
        "WHERE LOWER(TRIM(persons_name))=LOWER(TRIM(%s)) "
        "AND persons_status != 'merged' AND persons_type = 'person' ORDER BY persons_created_at",
        (name,),
    )
    return list(cur.fetchall())


def _mbid_index() -> dict[str, str]:
    if not MB.exists():
        return {}
    data = json.loads(MB.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in data:
        mb = row.get("musicbrainz") or {}
        if mb.get("status") == "match" and mb.get("mbid"):
            out[str(row.get("persons_name") or "").casefold()] = mb["mbid"]
    return out


def _confirm(name: str, existing_ids: set[tuple[str, str]], mbid: str | None) -> tuple[bool, str]:
    if mbid and ("musicbrainz", mbid) in existing_ids or mbid and ("mbid", mbid) in existing_ids:
        return True, f"musicbrainz:{mbid}"
    for r in _viaf(name):
        if _norm(str(r.get("displayForm") or "")) != _norm(name):
            continue
        viaf = str(r.get("viafid") or "")
        if viaf and ("viaf", viaf) in existing_ids:
            return True, f"viaf:{viaf}"
    for r in _gnd(name):
        if _norm(str(r.get("preferredName") or "")) != _norm(name):
            continue
        gnd = str(r.get("gndIdentifier") or "")
        if gnd and ("gnd", gnd) in existing_ids:
            return True, f"gnd:{gnd}"
    for r in _wikidata(name):
        if _norm(str(r.get("label") or "")) != _norm(name):
            continue
        qid = str(r.get("id") or "")
        if qid and ("wikidata_qid", qid) in existing_ids:
            return True, f"wikidata:{qid}"
    return False, ""


def _merge(cur, fake: str, target: str) -> None:
    cur.execute("SELECT * FROM works_person_roles WHERE works_person_roles_person_id=%s", (fake,))
    for row in cur.fetchall():
        cur.execute(
            "SELECT works_person_roles_id FROM works_person_roles WHERE works_person_roles_work_id=%s "
            "AND works_person_roles_role_id=%s AND works_person_roles_person_id=%s",
            (row["works_person_roles_work_id"], row["works_person_roles_role_id"], target),
        )
        if cur.fetchone():
            cur.execute(
                "DELETE FROM works_person_roles WHERE works_person_roles_id=%s", (row["works_person_roles_id"],)
            )
        else:
            cur.execute(
                "UPDATE works_person_roles SET works_person_roles_person_id=%s WHERE works_person_roles_id=%s",
                (target, row["works_person_roles_id"]),
            )
    cur.execute("SELECT * FROM persons_identity WHERE persons_id=%s", (fake,))
    for row in cur.fetchall():
        cur.execute(
            "SELECT id FROM persons_identity WHERE persons_id=%s AND identity_type=%s AND identity_value=%s LIMIT 1",
            (target, row["identity_type"], row["identity_value"]),
        )
        if cur.fetchone():
            cur.execute("DELETE FROM persons_identity WHERE id=%s", (row["id"],))
        else:
            cur.execute("UPDATE persons_identity SET persons_id=%s WHERE id=%s", (target, row["id"]))
    cur.execute(
        "UPDATE persons SET persons_status='merged', persons_merged_into=%s, persons_merged_at=NOW(6), "
        "persons_visible=0, persons_updated_at=NOW(6) WHERE persons_id=%s",
        (target, fake),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-confidence", type=float, default=0.9)
    args = ap.parse_args()
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    mbids = _mbid_index()
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    conn = pymysql.connect(
        host=conf["host"],
        port=conf["port"],
        user=conf["user"],
        password=conf["password"],
        database=conf["name"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    report: list[dict[str, Any]] = []
    merged = conflicts = 0
    try:
        with conn.cursor() as cur:
            for d in decisions:
                composer = str(d.get("composer") or "").strip()
                if d.get("action") != "rename" or not composer or float(d.get("confidence") or 0) < args.min_confidence:
                    continue
                if "&" in composer or " and " in composer.casefold() or ";" in composer:
                    continue
                targets = [p for p in _existing(cur, composer) if p["persons_id"] != d.get("persons_id")]
                if not targets:
                    continue
                target = targets[0]
                fake_ids = _identities(cur, str(d["persons_id"]))
                target_ids = _identities(cur, str(target["persons_id"]))
                mbid = mbids.get(composer.casefold())
                ok, evidence = _confirm(composer, target_ids, mbid)
                conflicts += 1
                if ok and args.apply:
                    _merge(cur, str(d["persons_id"]), str(target["persons_id"]))
                    merged += 1
                report.append(
                    {
                        "fake_id": d["persons_id"],
                        "fake_name": composer,
                        "target_id": target["persons_id"],
                        "target_name": target["persons_name"],
                        "confirmed": ok,
                        "evidence": evidence,
                        "fake_identities": len(fake_ids),
                        "target_identities": len(target_ids),
                    }
                )
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    _save_cache()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "fake_id",
            "fake_name",
            "target_id",
            "target_name",
            "confirmed",
            "evidence",
            "fake_identities",
            "target_identities",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report)
    confirmed = sum(1 for r in report if r["confirmed"])
    print(f"conflictos={conflicts} confirmados={confirmed} fusionados={merged}")
    print(f"informe={REPORT}")
    print("BD actualizada" if args.apply else "DRY-RUN: usa --apply para fusionar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


