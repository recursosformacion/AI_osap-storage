"""Resuelve los compositores restantes de `works_person_import` buscando por la obra.

Para cada fila pendiente (rol `composer`) no resuelta:
  1. Toma el **título de la obra** (`works.works_title`) y el nombre actual del import.
  2. Lanza una **búsqueda web** (proxy `r.jina.ai` sobre DuckDuckGo HTML, configurable con
     `OSAP_SEARCH_URL`).
  3. Busca en los resultados **compositores conocidos** (personas existentes o entradas de
     `persons_authority`, por nombre completo normalizado).
     - Si aparece **exactamente uno**, se acepta: se crea/enlaza la persona (si no existía,
       se da de alta desde la autoridad con sus identificadores), se crea la fila en
       `works_person_roles` (rol 1) y se marca `works_person_import_resolved = 1`.
     - Si aparecen varios o ninguno, la fila queda pendiente y se anota en el CSV de
       revisión (`--review-csv`), con la evidencia.

Requisitos: red. Uso:
    .venv\\Scripts\\python.exe scripts/resolve_composers_web.py --limit 20 --dry-run
    .venv\\Scripts\\python.exe scripts/resolve_composers_web.py --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import os
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_names import normalize_composer_name  # noqa: E402
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from incorporate_from_authority import SOURCE_SYSTEM  # noqa: E402
from link_works_person_import import ROLE_IDS, clean_raw, compact  # noqa: E402

_SEARCH_URL = os.environ.get(
    "OSAP_SEARCH_URL", "https://r.jina.ai/http://html.duckduckgo.com/html/?q={q}"
)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _plain(html: str) -> str:
    return _WS.sub(" ", _TAGS.sub(" ", html or "")).strip()


async def search(client: httpx.AsyncClient, query: str) -> str:
    url = _SEARCH_URL.format(q=httpx.QueryParams({"q": query})["q"])
    resp = await client.get(url, timeout=25)
    resp.raise_for_status()
    return _plain(resp.text)


async def run(
    db_name: str,
    roles: list[str],
    limit: int | None,
    dry_run: bool,
    review_csv: Path,
    delay: float,
) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    by_norm: dict[str, set[str]] = defaultdict(set)
    by_compact: dict[str, set[str]] = defaultdict(set)
    work_count: dict[str, int] = {}
    known: dict[str, tuple[str, str, dict | None]] = {}  # norm -> (kind, pid/name, auth)

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT persons_id, persons_name FROM persons")
        for r in await cur.fetchall():
            by_norm[normalize_composer_name(r["persons_name"])].add(r["persons_id"])
            by_compact[compact(r["persons_name"])].add(r["persons_id"])
            known.setdefault(
                normalize_composer_name(r["persons_name"]), ("person", r["persons_id"], None)
            )
        await cur.execute(
            "SELECT person_id, person_aliases_normalized_alias, person_aliases_alias "
            "FROM persons_aliases"
        )
        for r in await cur.fetchall():
            by_norm[str(r["person_aliases_normalized_alias"])].add(r["person_id"])
            by_compact[compact(r["person_aliases_alias"])].add(r["person_id"])
        await cur.execute(
            "SELECT works_person_roles_person_id AS pid, COUNT(*) AS n "
            "FROM works_person_roles WHERE works_person_roles_role_id = 1 "
            "GROUP BY works_person_roles_person_id"
        )
        work_count = {str(r["pid"]): int(r["n"]) for r in await cur.fetchall()}
        await cur.execute(
            "SELECT authority_id, persons_authority_canonical_name AS name, "
            "persons_authority_wikidata_id AS wid, persons_authority_viaf_id AS viaf, "
            "persons_authority_imslp_id AS imslp FROM persons_authority"
        )
        for r in await cur.fetchall():
            key = normalize_composer_name(r["name"])
            if key:
                known.setdefault(
                    key,
                    ("authority", str(r["name"]),
                     {"authority_id": r["authority_id"], "wikidata_id": r["wid"],
                      "viaf_id": r["viaf"], "imslp_id": r["imslp"]}),
                )

        roles_ph = ", ".join(["%s"] * len(roles))
        sql = (
            f"SELECT i.id, i.works_id, i.works_person_import_name AS name, "
            f"i.works_person_import_role AS role, w.works_title AS title "
            f"FROM works_person_import i JOIN works w ON w.id = i.works_id "
            f"WHERE i.works_person_import_resolved = 0 "
            f"AND i.works_person_import_role IN ({roles_ph}) "
            f"AND w.works_title IS NOT NULL AND w.works_title <> '' "
            f"ORDER BY i.id"
        )
        params: list = list(roles)
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    # Nombres largos para buscar en el texto (evita falsos positivos de nombres cortos).
    needles = {k: v for k, v in known.items() if len(k) >= 8}
    print(f"filas a buscar: {len(rows)} | nombres conocidos indexados: {len(needles)}")

    links: list[tuple[int, str, int]] = []
    resolved_ids: list[int] = []
    new_persons: list[tuple[str, str, dict | None]] = []
    review: list[dict] = []
    stats = {"aceptadas": 0, "multiples": 0, "sin_pista": 0, "error_red": 0}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for i, r in enumerate(rows, 1):
            title = str(r["title"]).strip()
            raw_name = clean_raw(str(r["name"]))
            query = f'"{title}" composer'
            try:
                text = normalize_composer_name(await search(client, query))
            except Exception as exc:  # red caída o bloqueo
                stats["error_red"] += 1
                review.append({"import_id": r["id"], "works_id": r["works_id"],
                               "title": title, "current": raw_name,
                               "motivo": f"error_busqueda: {exc}"})
                continue
            finally:
                await asyncio.sleep(delay)

            hits = [k for k in needles if k in text]
            if len(hits) == 1:
                key = hits[0]
                kind, ref, auth = known[key]
                if kind == "person":
                    pid = ref
                else:
                    candidates = by_norm.get(key) or set()
                    if len(candidates) == 1:
                        pid = next(iter(candidates))
                    elif len(candidates) > 1:
                        ranked = sorted(candidates, key=lambda p: (-work_count.get(p, 0), p))
                        pid = (
                            ranked[0]
                            if work_count.get(ranked[0], 0) > work_count.get(ranked[1], 0)
                            else None
                        )
                    else:
                        pid = None
                    if pid is None:
                        pid = str(uuid.uuid4())
                        new_persons.append((pid, ref, auth))
                        by_norm.setdefault(key, set()).add(pid)
                links.append((int(r["works_id"]), pid, ROLE_IDS[str(r["role"])]))
                resolved_ids.append(int(r["id"]))
                stats["aceptadas"] += 1
            elif len(hits) > 1:
                stats["multiples"] += 1
                review.append({"import_id": r["id"], "works_id": r["works_id"], "title": title,
                               "current": raw_name, "motivo": "varios: " + " | ".join(hits[:5])})
            else:
                stats["sin_pista"] += 1
                review.append({"import_id": r["id"], "works_id": r["works_id"], "title": title,
                               "current": raw_name, "motivo": "sin coincidencia"})

            if i % 25 == 0:
                print(f"  ... {i}/{len(rows)} aceptadas={stats['aceptadas']}")

    print(stats, "| personas nuevas:", len(new_persons))

    with review_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["import_id", "works_id", "title", "current", "motivo"])
        w.writeheader()
        w.writerows(review)
    print(f"revisión -> {review_csv} ({len(review)} filas)")

    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for pid, name, auth in new_persons:
            await cur.execute(
                "INSERT IGNORE INTO persons (persons_id, persons_name, persons_visible, "
                "persons_status, persons_source_system) VALUES (%s, %s, 1, 'active', %s)",
                (pid, name, SOURCE_SYSTEM),
            )
            if auth:
                for id_type, value in (
                    ("wikidata_qid", auth.get("wikidata_id")),
                    ("viaf", auth.get("viaf_id")),
                    ("imslp", auth.get("imslp_id")),
                ):
                    if value:
                        await cur.execute(
                            "INSERT INTO persons_identifiers (persons_id, "
                            "persons_identifiers_type, persons_identifiers_value, "
                            "persons_identifiers_source) VALUES (%s, %s, %s, 'wikidata')",
                            (pid, id_type, str(value)),
                        )
                if auth.get("authority_id"):
                    await cur.execute(
                        "UPDATE persons_authority SET persons_id = %s "
                        "WHERE authority_id = %s AND persons_id IS NULL",
                        (pid, auth["authority_id"]),
                    )
        if links:
            await cur.executemany(
                "INSERT IGNORE INTO works_person_roles (works_person_roles_work_id, "
                "works_person_roles_person_id, works_person_roles_role_id) VALUES (%s,%s,%s)",
                links,
            )
        for j in range(0, len(resolved_ids), 1000):
            chunk = resolved_ids[j : j + 1000]
            ph = ", ".join(["%s"] * len(chunk))
            await cur.execute(
                f"UPDATE works_person_import SET works_person_import_resolved = 1 "
                f"WHERE id IN ({ph})",
                chunk,
            )
    await db.close()
    print(f"personas nuevas: {len(new_persons)} | relaciones: {len(links)} | "
          f"marcadas: {len(resolved_ids)}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--roles", default="composer")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--delay", type=float, default=2.0, help="segundos entre búsquedas")
    ap.add_argument("--review-csv", type=Path, default=Path("web_review.csv"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    asyncio.run(run(args.db, roles, args.limit, args.dry_run, args.review_csv, args.delay))


if __name__ == "__main__":
    main()
