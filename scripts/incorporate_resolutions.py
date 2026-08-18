#!/usr/bin/env python
"""Incorporar resultados de resolución de identidad en el Maestro (osap-storage).

A partir de `composer_identity_resolution` (una pasada del identity_resolver), crea
Composer agrupando POR IDENTIDAD (no una entidad por obra):

  matched_existing     -> asociar obras al Composer existente (evidencia.maestro)
  resolved_by_*        -> agrupar por viaf/mbid/qid -> crear Composer UNA vez
                          (aliases + identifiers + evidence) y asociar todas sus obras
  ambiguous            -> placeholder Composer hidden (visible=0, review requerida), sin obras
  unknown              -> se conserva el resultado, NO se crea entidad

Uso:
    python scripts/incorporate_resolutions.py \
        --db osap_storage [--db-user osap] [--db-password ...] \
        --test prod-10000-001 [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_ANON = {
    "anon", "anon.", "anonymous", "trad", "trad.", "traditional", "attrib.", "attributed",
    "attrib", "unknown", "author unknown", "urheber unbekannt", "urheber unbek.",
    "na", "n/a", "n.a.", "none", "composer",
}
_RESOLVED = {"resolved_by_mbid", "resolved_by_viaf", "resolved_by_qid_plus_evidence",
             "resolved_by_name_dates"}
_SOURCE = "identity-resolver"


def composer_key(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    low = text.lower().replace("'", "").replace("\u2019", "")
    if low in _ANON or low.startswith("urheber unbekannt"):
        return "anonymous"
    text = re.sub(r"\s+\d{3,4}\s*$", "", text)
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


def _clean_name(raw: str) -> str:
    text = re.sub(r"\s+\d{3,4}\s*$", "", (raw or "").strip())
    text = re.sub(r"\([^)]*\)", "", text)
    return text.strip()


def _year(date: str | None) -> str | None:
    if not date:
        return None
    m = re.match(r"(\d{4})", date)
    return m.group(1) if m else None


def _identity_payload(status: str, reason: str, ev: dict) -> dict | None:
    """Devuelve {key, name, viaf, qid, mbid, isni, aliases, birth, death} o None."""
    open_rec = ev.get("open") or {}
    authority = ev.get("authority") or []
    viaf = reason and re.search(r"viaf=([A-Za-z0-9]+)", reason)
    viaf = viaf.group(1) if viaf else (open_rec.get("viaf") or (authority[0].get("viaf") if authority else None))
    qid = open_rec.get("qid") or (authority[0].get("qid") if authority else None)
    mbid = open_rec.get("mbid")
    isni = open_rec.get("isni")
    name = open_rec.get("canonical_name") or (authority[0].get("name") if authority else None)
    birth = authority[0].get("birth") if authority else None
    death = authority[0].get("death") if authority else None
    aliases = list(open_rec.get("aliases") or [])
    for a in authority:
        if a.get("name") and a["name"] != name:
            aliases.append(a["name"])
    if viaf:
        key = f"viaf:{viaf}"
    elif mbid:
        key = f"mbid:{mbid}"
    elif qid:
        key = f"qid:{qid}"
    else:
        return None
    return {"key": key, "name": name, "viaf": viaf, "qid": qid, "mbid": mbid,
            "isni": isni, "aliases": aliases, "birth": birth, "death": death,
            "strong": bool(viaf or mbid)}


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", default="prod-10000-001")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-host", default="127.0.0.1")
    parser.add_argument("--db-user", default="osap2027")
    parser.add_argument("--db-password", default="2027osapdb")
    parser.add_argument("--db-name", default="osap-storage")
    args = parser.parse_args()

    db = {
        "host": args.db_host, "user": args.db_user, "password": args.db_password,
        "database": args.db_name, "charset": "utf8mb4", "cursorclass": pymysql.cursors.DictCursor,
    }
    conn = pymysql.connect(**db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT work_id, attribution, status, decision_reason, evidence_json "
                "FROM composer_identity_resolution WHERE test_id=%s", (args.test,))
            rows = cur.fetchall()

        match_groups: dict[str, list[int]] = defaultdict(list)      # composer_id -> [work_ids]
        identity_groups: dict[str, dict] = defaultdict(lambda: {"works": [], "sample": None})
        ambiguous_groups: dict[str, dict] = defaultdict(lambda: {"works": [], "reason": None})
        counts = {"matched_existing": 0, "resolved": 0, "ambiguous": 0, "unknown": 0,
                  "resolved_without_identity": 0}
        for r in rows:
            status = r["status"]
            work_id = int(r["work_id"])
            ev = json.loads(r["evidence_json"]) if isinstance(r["evidence_json"], str) else (r["evidence_json"] or {})
            reason = r["decision_reason"] or ""
            if status == "matched_existing":
                maestro = ev.get("maestro") or {}
                cid = maestro.get("composer_id")
                if cid:
                    match_groups[cid].append(work_id)
                    counts["matched_existing"] += 1
                else:
                    counts["unknown"] += 1
            elif status in _RESOLVED:
                payload = _identity_payload(status, reason, ev)
                if payload:
                    identity_groups[payload["key"]]["works"].append(work_id)
                    if identity_groups[payload["key"]]["sample"] is None:
                        identity_groups[payload["key"]]["sample"] = payload
                    counts["resolved"] += 1
                else:
                    counts["resolved_without_identity"] += 1
            elif status == "ambiguous":
                key = composer_key(r["attribution"])
                g = ambiguous_groups[key]
                g["works"].append(work_id)
                g["reason"] = reason or "ambiguous VIAF"
                g.setdefault("sample", r["attribution"])
                counts["ambiguous"] += 1
            else:
                counts["unknown"] += 1

        n_match_works = sum(len(v) for v in match_groups.values())
        n_identity_works = sum(len(v["works"]) for v in identity_groups.values())
        n_strong = sum(1 for g in identity_groups.values() if g["sample"]["strong"])
        n_weak = len(identity_groups) - n_strong
        print(f"=== INCORPORAR {args.test} ({'DRY-RUN' if args.dry_run else 'EJECUTANDO'}) ===")
        print(f"  matched_existing: {counts['matched_existing']} obras -> {len(match_groups)} compositores existentes")
        print(f"  resolved: {counts['resolved']} obras -> {len(identity_groups)} identidades únicas")
        print(f"     fuertes (viaf/mbid, visibles): {n_strong} | débiles (solo qid, hidden+review): {n_weak}")
        print(f"  resolved sin identidad: {counts['resolved_without_identity']}")
        print(f"  ambiguous: {counts['ambiguous']} obras -> {len(ambiguous_groups)} atribuciones distintas (hidden)")
        print(f"  unknown (sin crear): {counts['unknown']}")

        if args.dry_run:
            print("\n[DRY-RUN] Muestra de identidades a crear (nombre | viaf | qid | obras):")
            for i, (_k, g) in enumerate(sorted(identity_groups.items())):
                if i >= 12:
                    break
                s = g["sample"]
                line = f"   {s['name']} | viaf={s['viaf']} qid={s['qid']} mbid={s.get('mbid')}"
                print(f"{line} | {len(g['works'])} obras")
            print(f"  ... y {len(ambiguous_groups)} atribuciones ambiguous -> hidden placeholders")
            return 0

        # --- asociar matched_existing ---
        with conn.cursor() as cur:
            pairs = [(cid, wid) for cid, wids in match_groups.items() for wid in wids]
            if pairs:
                cur.executemany("UPDATE works SET composer_id=%s WHERE id=%s", pairs)
            # --- identidades ---
            created = 0
            reused = 0
            created_strong = 0
            created_weak = 0
            for _key, g in identity_groups.items():
                s = g["sample"]
                cid = _find_existing(cur, s)
                if cid:
                    reused += 1
                    for wid in g["works"]:
                        cur.execute("UPDATE works SET composer_id=%s WHERE id=%s", (cid, wid))
                    continue
                cid = str(uuid.uuid4())
                visible = 1 if s["strong"] else 0
                cur.execute(
                    "INSERT INTO composers (id, name, visible, status, review_status, "
                    "musicbrainz_id, birth_year, death_year, source_system) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (cid, (s["name"] or "?"), visible, "active", "not_reviewed",
                     s["mbid"], _year(s["birth"]), _year(s["death"]), _SOURCE),
                )
                for alias in {a for a in ([s["name"]] + s["aliases"]) if a}:
                    cur.execute(
                        "INSERT IGNORE INTO composer_aliases (composer_id, alias, normalized_alias) "
                        "VALUES (%s,%s,%s)", (cid, alias, composer_key(alias)),
                    )
                ids = []
                for id_type, value in (("viaf", s["viaf"]), ("wikidata_qid", s["qid"]),
                                       ("mbid", s["mbid"]), ("isni", s["isni"])):
                    if value:
                        ids.append(id_type)
                        cur.execute(
                            "INSERT IGNORE INTO composer_identifiers "
                            "(composer_id, id_type, id_value, is_identity_anchor, source, strength) "
                            "VALUES (%s,%s,%s,%s,%s,'strong')",
                            (cid, id_type, value, 1 if id_type == "viaf" else 0, _SOURCE),
                        )
                cur.execute(
                    "INSERT INTO composer_evidence (composer_id, rule, decision, reason, "
                    "anchor_type, anchor_value, channels, identifiers_used, matcher_version) "
                    "VALUES (%s,'creation','auto',%s,'none','none','[]',%s,'identity-resolver')",
                    (cid, (s.get("reason") or "identity resolution")[:64], json.dumps(ids)),
                )
                for wid in g["works"]:
                    cur.execute("UPDATE works SET composer_id=%s WHERE id=%s", (cid, wid))
                created += 1
                if s["strong"]:
                    created_strong += 1
                else:
                    created_weak += 1
            # --- ambiguous -> hidden placeholders ---
            amb_created = 0
            for key, g in ambiguous_groups.items():
                cid = str(uuid.uuid4())
                name = _clean_name(g.get("sample") or key) or key
                cur.execute(
                    "INSERT INTO composers (id, name, visible, status, review_status, source_system) "
                    "VALUES (%s,%s,0,'active','not_reviewed',%s)",
                    (cid, name or key, _SOURCE),
                )
                cur.execute(
                    "INSERT INTO composer_evidence (composer_id, rule, decision, reason, "
                    "anchor_type, anchor_value, channels, identifiers_used, matcher_version) "
                    "VALUES (%s,'ambiguous','pending',%s,'none','none','[]','[]',"
                    "'identity-resolver')",
                    (cid, g["reason"][:64]),
                )
                amb_created += 1
            conn.commit()
        print(f"\n  creados: {created} (fuertes visibles: {created_strong} | débiles hidden: {created_weak}) "
              f"| reutilizados existentes: {reused} | ambiguous placeholders: {amb_created}")
        print(f"  obras asociadas (matched): {n_match_works} | (resolved): {n_identity_works}")
    finally:
        conn.close()
    return 0


def _find_existing(cur, s: dict) -> str | None:
    if s.get("mbid"):
        cur.execute("SELECT id FROM composers WHERE musicbrainz_id=%s LIMIT 1", (s["mbid"],))
        row = cur.fetchone()
        if row:
            return row["id"]
    for id_type, value in (("viaf", s["viaf"]), ("wikidata_qid", s["qid"]), ("mbid", s["mbid"])):
        if value:
            cur.execute(
                "SELECT composer_id FROM composer_identifiers WHERE id_type=%s AND id_value=%s LIMIT 1",
                (id_type, value))
            row = cur.fetchone()
            if row:
                return row["composer_id"]
    if s.get("name"):
        cur.execute("SELECT id FROM composers WHERE name=%s LIMIT 1", (s["name"],))
        row = cur.fetchone()
        if row:
            return row["id"]
    return None


if __name__ == "__main__":
    sys.exit(main())
