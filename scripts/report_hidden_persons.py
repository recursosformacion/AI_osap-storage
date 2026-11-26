"""Informe de personas OCULTAS con obras (colas de revisión y duplicados).

No escribe en la base de datos salvo que se use `--merge-exact --apply`. Clasifica:

- placeholder: Anonymous, Trad, Various, Composer, Urheber unbekannt...
- parse_junk: títulos/fechas/notas de transcripción pegados al nombre.
- duplicate_exact: mismo nombre normalizado que una persona visible con obras.
- duplicate_fuzzy: nombre muy parecido a una visible (posible variante Mac/Mc).
- unique: persona real sin duplicado evidente; candidata a revisión/enriquecimiento.

Uso:
    .venv/bin/python scripts/report_hidden_persons.py --csv /tmp/hidden.csv
    .venv/bin/python scripts/report_hidden_persons.py --merge-exact --apply --allow-prod
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import PROJECT_ROOT, Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

PLACEHOLDER = {
    "anonymous", "anon", "anon.", "trad", "trad.", "traditional", "tradicional",
    "various", "composer", "unknown", "urheber unbekannt",
}
ENSEMBLE_RE = re.compile(
    r"\b(band|choir|chorus|orchestra|ensemble|trio|quartet|quintet)\s*$", re.IGNORECASE
)
JUNK_PATTERNS = re.compile(
    r"(^['\"“”‘’]|"
    r"\b(Op\.|Datum|Page|Transcribed by|Untitled|No\s*\d+|vol\.|book|"
    r"published|collection of)\b|"
    r"\b1[5-9]\d{2}\b)",
    re.IGNORECASE,
)


def norm(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    value = value.casefold().replace("'", "").replace("\u2019", "")
    return re.sub(r"\s+", " ", value).strip()


def classify(name: str) -> str:
    low = norm(name).strip(" .,'\"")
    if not low or low in PLACEHOLDER or low.startswith("urheber unbekannt"):
        return "placeholder"
    if JUNK_PATTERNS.search(name or ""):
        return "parse_junk"
    return "unique"


def tokens(name: str) -> list[str]:
    return [t for t in norm(name).split() if len(t) >= 3]


async def load_rows(db: Database) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT p.persons_id, p.persons_name, p.persons_type, p.persons_source_system, "
            "p.persons_review_status, p.persons_birth_year, p.persons_death_year, "
            "CHAR_LENGTH(TRIM(COALESCE(p.persons_biography_summary,''))) AS bio_len, "
            "EXISTS (SELECT 1 FROM persons_identity i WHERE i.persons_id=p.persons_id "
            "AND i.identity_type IN ('viaf','wikidata_qid','imslp','musicbrainz','gnd',"
            "'rism','isni','bnf','lccn')) AS has_identity, "
            "COUNT(DISTINCT r.works_person_roles_work_id) AS works "
            "FROM persons p JOIN works_person_roles r ON "
            "r.works_person_roles_person_id=p.persons_id AND r.works_person_roles_role_id=1 "
            "WHERE p.persons_visible=0 GROUP BY p.persons_id "
            "ORDER BY works DESC, p.persons_name"
        )
        hidden = [dict(r) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT p.persons_id, p.persons_name, p.persons_birth_year, p.persons_death_year "
            "FROM persons p WHERE p.persons_visible=1 AND EXISTS ("
            "SELECT 1 FROM works_person_roles r WHERE "
            "r.works_person_roles_person_id=p.persons_id AND r.works_person_roles_role_id=1)"
        )
        visible = [dict(r) for r in await cur.fetchall()]
    return hidden, visible


def build_index(visible: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    exact: dict[str, dict[str, Any]] = {}
    by_token: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in visible:
        key = norm(row["persons_name"])
        if key:
            exact.setdefault(key, row)
        for token in set(tokens(row["persons_name"])):
            by_token[token].append(row)
    return exact, by_token


def find_fuzzy(row: dict[str, Any], by_token: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    key = norm(row["persons_name"])
    candidates: dict[str, dict[str, Any]] = {}
    for token in tokens(row["persons_name"]):
        for candidate in by_token.get(token, []):
            candidates[candidate["persons_id"]] = candidate
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for candidate in list(candidates.values())[:200]:
        score = difflib.SequenceMatcher(None, key, norm(candidate["persons_name"])).ratio()
        if score > best[0]:
            best = (score, candidate)
    return best[1] if best[0] >= 0.94 else None


async def merge_exact(db: Database, groups: dict[str, list[dict[str, Any]]], apply: bool) -> dict[str, int]:
    merged = skipped = links = 0
    backup: list[dict[str, Any]] = []
    async with db.transaction() as conn, conn.cursor() as cur:
        for canonical_id, rows in groups.items():
            for row in rows:
                await cur.execute(
                    "SELECT works_person_roles_work_id, works_person_roles_role_id "
                    "FROM works_person_roles WHERE works_person_roles_person_id=%s",
                    (row["persons_id"],),
                )
                row_links = [dict(r) for r in await cur.fetchall()]
                backup.append({"person": row, "links": row_links})
                if not apply:
                    continue
                if any(int(link["works_person_roles_role_id"]) != 1 for link in row_links):
                    skipped += 1
                    continue
                for link in row_links:
                    if int(link["works_person_roles_role_id"]) == 1:
                        await cur.execute(
                            "INSERT IGNORE INTO works_person_roles "
                            "(works_person_roles_work_id, works_person_roles_person_id, "
                            "works_person_roles_role_id) VALUES (%s,%s,1)",
                            (link["works_person_roles_work_id"], canonical_id),
                        )
                        links += 1
                await cur.execute("DELETE FROM persons_aliases WHERE person_id=%s", (row["persons_id"],))
                await cur.execute(
                    "DELETE FROM persons_identity WHERE persons_id=%s", (row["persons_id"],)
                )
                await cur.execute(
                    "DELETE FROM persons_evidence WHERE persons_id=%s", (row["persons_id"],)
                )
                await cur.execute(
                    "DELETE FROM works_person_roles WHERE works_person_roles_person_id=%s",
                    (row["persons_id"],),
                )
                await cur.execute("DELETE FROM persons WHERE persons_id=%s", (row["persons_id"],))
                merged += 1
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = PROJECT_ROOT / "var" / f"hidden_persons_merge_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"applied": apply, "merged": merged, "backup": backup},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"backup: {path}")
    return {"merged": merged, "skipped": skipped, "links": links}


async def promote(db: Database, rows: list[dict[str, Any]], *, apply: bool) -> dict[str, int]:
    ids = [row["persons_id"] for row in rows]
    if not ids:
        return {"promoted": 0}
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = PROJECT_ROOT / "var" / f"hidden_persons_promote_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"applied": apply, "count": len(rows), "persons": rows},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    if not apply:
        return {"promoted": 0, "would_promote": len(ids)}
    placeholders = ", ".join(["%s"] * len(ids))
    async with db.transaction() as conn, conn.cursor() as cur:
        await cur.execute(
            f"UPDATE persons SET persons_visible=1, persons_updated_at=NOW(6) "
            f"WHERE persons_id IN ({placeholders})",
            ids,
        )
        await cur.executemany(
            "INSERT INTO persons_evidence (persons_id, persons_evidence_rule, "
            "persons_evidence_decision, persons_evidence_reason, persons_evidence_anchor_type, "
            "persons_evidence_anchor_value, persons_evidence_channels, "
            "persons_evidence_identifiers_used, persons_evidence_matcher_version) "
            "VALUES (%s,'visibility-review','promote','reviewed_with_data','none','none',"
            "'[\"reviewed\"]','[]','visibility-v1')",
            [(person_id,) for person_id in ids],
        )
    return {"promoted": len(ids), "backup": str(path)}


async def main_async(args: argparse.Namespace) -> int:
    settings = Settings()
    db = Database(settings.model_copy(update={"db_name": args.db}))
    await db.connect()
    hidden, visible = await load_rows(db)
    exact, by_token = build_index(visible)
    rows: list[dict[str, Any]] = []
    for row in hidden:
        key = norm(row["persons_name"])
        classification = classify(row["persons_name"])
        duplicate = exact.get(key) if key else None
        if classification == "unique" and duplicate is None:
            fuzzy = find_fuzzy(row, by_token)
            if fuzzy is not None:
                classification = "duplicate_fuzzy"
                duplicate = fuzzy
            elif duplicate is None:
                classification = "unique"
        elif duplicate is not None and classification == "unique":
            classification = "duplicate_exact"
        row = {
            **row,
            "classification": classification,
            "duplicate_of": duplicate["persons_id"] if duplicate else "",
            "duplicate_name": duplicate["persons_name"] if duplicate else "",
        }
        rows.append(row)

    counts = Counter(r["classification"] for r in rows)
    by_source = Counter(r["persons_source_system"] for r in rows)
    print("ocultas con obras:", len(rows))
    print("clasificación:", dict(counts))
    print("fuentes:", dict(by_source))
    print("\nTop 40 por obras:")
    for row in rows[:40]:
        print(
            f"{row['works']:>6}  {row['classification']:<16}  {row['persons_name'][:60]:<60}"
            f"  {row['duplicate_name'][:40]}"
        )

    if args.csv:
        path = Path(args.csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(rows[0].keys()) if rows else [
            "persons_id", "persons_name", "persons_source_system", "persons_review_status",
            "persons_birth_year", "persons_death_year", "works", "classification",
            "duplicate_of", "duplicate_name",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"csv: {path}")
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"json: {path}")

    if args.promote:
        candidates = [
            row for row in rows
            if row["classification"] == "unique"
            and row["persons_review_status"] == "reviewed"
            and int(row["works"]) >= args.min_works
            and (row.get("persons_type") or "person") == "person"
            and not ENSEMBLE_RE.search(row["persons_name"] or "")
            and (
                row["persons_birth_year"]
                or row["persons_death_year"]
                or row["has_identity"]
                or int(row["bio_len"] or 0) >= 80
            )
        ]
        candidates.sort(key=lambda row: int(row["works"]), reverse=True)
        if args.limit:
            candidates = candidates[: args.limit]
        print(f"\npromovibles (reviewed + datos): {len(candidates)}")
        for row in candidates[:30]:
            print(
                f"{row['works']:>6}  {row['persons_name'][:60]:<60}"
                f"  {row['persons_birth_year'] or ''}-{row['persons_death_year'] or ''}"
            )
        if args.apply and not args.allow_prod:
            print("--apply requiere --allow-prod")
        elif candidates:
            print(await promote(db, candidates, apply=args.apply))

    if args.merge_exact:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row["classification"] != "duplicate_exact" or not row["duplicate_of"]:
                continue
            duplicate = next(v for v in visible if v["persons_id"] == row["duplicate_of"])
            if (
                row["persons_birth_year"]
                and duplicate["persons_birth_year"]
                and row["persons_birth_year"] != duplicate["persons_birth_year"]
            ):
                continue
            if (
                row["persons_death_year"]
                and duplicate["persons_death_year"]
                and row["persons_death_year"] != duplicate["persons_death_year"]
            ):
                continue
            groups[row["duplicate_of"]].append(row)
        total = sum(len(v) for v in groups.values())
        print(f"duplicados exactos fusionables: {total} en {len(groups)} canónicos")
        if args.apply and not args.allow_prod:
            print("--apply requiere --allow-prod")
        elif groups:
            result = await merge_exact(db, groups, apply=args.apply)
            print(result)
    await db.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="osap_storage")
    parser.add_argument("--csv")
    parser.add_argument("--json-out")
    parser.add_argument("--promote", action="store_true", help="Propone hacer visibles personas revisadas con datos")
    parser.add_argument("--min-works", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0, help="Máximo de personas a promover (0 = todas)")
    parser.add_argument("--merge-exact", action="store_true", help="Prepara/fusiona duplicados exactos")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-prod", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
