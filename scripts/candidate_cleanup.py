#!/usr/bin/env python
"""Limpieza de candidatos a Composer (fase previa a resolver).

Clasifica las atribuciones `unknown` de `composer_identity_resolution` en categorías
para decidir qué se resuelve con identity-resolver y qué se descarta:

  mojibake   -> encoding corrupto (Yohei Kato åè æå¹³). NO crear Composer.
  no_persona -> no representan una persona (Tradicional, band, manuscrito...). NO crear.
  qualifier  -> prefijos tipo "after / arr. / attr. / harm." (no es el nombre real). NO crear.
  real       -> nombre limpio de persona probable (sí candidato).
  review     -> ambiguo/dudoso, se conserva para revisión.

Reusa `classify_composer_name` / `is_mojibake` / `clean_composer_name` de osap-storage.
Persiste el resultado en `composer_candidate` (migración 027).

Uso:
    python scripts/candidate_cleanup.py --db osap_storage \
        [--db-user osap] [--db-password ...] [--test prod-10000-001] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_quality import (  # noqa: E402
    REVIEW_CORRECT,
    REVIEW_INCORRECT,
    classify_composer_name,
    clean_composer_name,
    is_mojibake,
)

_ANON = {
    "anon", "anon.", "anonymous", "trad", "trad.", "traditional", "tradicional",
    "traditionell", "traditionel", "traditionnel", "traditionnelle", "anonim", "anonimo",
    "anônimo", "attrib.", "attributed", "attrib", "unknown", "author unknown",
    "urheber unbekannt", "urheber unbek.", "na", "n/a", "n.a.", "none", "composer",
    "unattributed", "moderate", "unbekannt",
}

_QUALIFIER_PATTERNS = [
    r"^after\b", r"^arr\.?\b", r"^attr\.?\b", r"^attributed to\b", r"^probably\b",
    r"^possibly\b", r"^doubtful\b", r"^harmonisat", r"^harmonization of\b",
    r"^based on\b", r"^from\b", r"^par\b", r"^nach\b", r"^by\b",
]

_NO_PERSONA_PATTERNS = [
    r"\b(symphony|symphonie|sonata|concerto|quartet|quintet|trio|duet|song|tune|melody|march|dance|nocturne|prelude|fugue|oratorio|requiem|mass|opera|operetta|chorale)\b",
    r"\b(band|orchestra|ensemble|chorus|choir|consort|capella)\b",
    r"\b(book|manuscript|handschrift|collection|codex|libro|chansonnier|anthology)\b",
    r"\b(sioux|thysius|vermell de montserrat|schemellis)\b",
    # --- ruido de campo composer (procedencia/traducción/tonada) ---
    r"^bij een",                                  # holandés "recopilado por"
    r"^hand of ",                                 # copista "en la mano de"
    r"^in hand\b", r"\bin hand [a-z]\b",          # "en la mano X" (manuscrito)
    r"untitled",                                  # "sin título"
    r"\bin ms\b", r"\bms\.?\b",                   # "en manuscrito"
    r"^old scotch", r"very old scotch",           # etiquetas de tonada
    r"\bscotch\b|\bsthrewpence\b",                # tonadas escocesas
    r"^trad\b", r"\btrad\.?\b",
    r"traditional (irish|shetland|folk|scottish|scot|welsh)",
    r"\b(compiled|collected|assembled|gathered|selected|arranged) by\b",
    r"\b(manuscript|scribe|copist|compiler|provenance)\b",
    r"^de prins frans",
    r"\b(hornpipe|reel|jig|strathspey|waltz|polka|galop)\b",   # formas/tonadas
]


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


def classify(name: str) -> tuple[str, str]:
    """Devuelve (label, verdict)."""
    low = name.lower().strip()
    if low in _ANON or low.startswith("urheber unbekannt"):
        return "no_persona", REVIEW_INCORRECT
    if is_mojibake(name):
        return "mojibake", REVIEW_INCORRECT
    if any(re.search(p, low) for p in _QUALIFIER_PATTERNS):
        return "qualifier", REVIEW_INCORRECT
    if any(re.search(p, low) for p in _NO_PERSONA_PATTERNS):
        return "no_persona", REVIEW_INCORRECT
    s = name.strip()
    if s[:1] in ('"', "\u201c") or s[-1:] in ('"', "\u201d"):
        return "no_persona", REVIEW_INCORRECT  # entrecomillado -> no persona
    cleaned = clean_composer_name(name)
    if not cleaned or not any(c.isalpha() for c in cleaned):
        return "no_persona", REVIEW_INCORRECT
    words = [w for w in cleaned.split() if w]
    # solo iniciales (J., J S, A B C) o muy corto (<=2 letras) -> no persona
    if not words or all(len(w) <= 1 for w in words) or len("".join(words)) <= 2:
        return "no_persona", REVIEW_INCORRECT
    verdict = classify_composer_name(name)
    if verdict == REVIEW_CORRECT:
        return "real", verdict
    if verdict == REVIEW_INCORRECT:
        return "no_persona", verdict
    return "review", verdict


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
                "SELECT attribution, COUNT(*) AS obras "
                "FROM composer_identity_resolution WHERE test_id=%s AND status='unknown' "
                "GROUP BY attribution ORDER BY obras DESC", (args.test,))
            rows = cur.fetchall()

        counts: Counter = Counter()
        real: list[dict] = []
        for r in rows:
            attribution = r["attribution"]
            obras = int(r["obras"])
            label, verdict = classify(attribution)
            counts[label] += 1
            if label == "real":
                real.append({"attribution": attribution, "obras": obras, "label": label,
                             "verdict": verdict, "key": composer_key(attribution),
                             "cleaned": clean_composer_name(attribution)})

        print(f"=== LIMPIEZA CANDIDATOS {args.test} ({'DRY-RUN' if args.dry_run else 'EJECUTANDO'}) ===")
        print(f"  total atribuciones unknown: {len(rows):,}")
        for label in ("real", "review", "no_persona", "qualifier", "mojibake"):
            if counts[label]:
                print(f"  {label:12}: {counts[label]:,}")
        print(f"\n  Candidatos reales: {len(real):,} | obras que cubrirían: {sum(x['obras'] for x in real):,}")
        if args.dry_run:
            print("\n  Top reales (prioridad por obras):")
            for x in real[:15]:
                print(f"     {x['obras']:>5}  {x['attribution'][:60]}")
            print("\n  Muestra de descartados:")
            shown = 0
            for r in rows:
                attribution = r["attribution"]
                label, _ = classify(attribution)
                if label in ("mojibake", "no_persona", "qualifier") and shown < 12:
                    print(f"     [{label:10}] {attribution[:60]}")
                    shown += 1
            return 0

        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM composer_candidate WHERE 1=1")  # repoblar (idempotente)
            inserted = 0
            for r in rows:
                attribution = r["attribution"]
                obras = int(r["obras"])
                label, verdict = classify(attribution)
                if label not in ("real", "review"):
                    continue  # descartados (mojibake/no_persona/qualifier) no crean Composer
                cur.execute(
                    "INSERT INTO composer_candidate (attribution, name_key, cleaned_name, "
                    "work_count, label, verdict) VALUES (%s,%s,%s,%s,%s,%s)",
                    (attribution, composer_key(attribution), clean_composer_name(attribution) or None,
                     obras, label, verdict),
                )
                inserted += 1
            conn.commit()
        print(f"\n  persistido en composer_candidate ({inserted:,} candidatos reales+review)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
