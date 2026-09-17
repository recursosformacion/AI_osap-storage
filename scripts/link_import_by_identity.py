"""Enlaza las filas pendientes de `works_person_import` con las personas del catálogo de
identidad, **sin crear alias ni personas nuevas**.

Usa `persons_identity`: los candidatos ya vinculados (`persons_id` no nulo) y las filas
canónicas de persona dan un mapa **nombre normalizado → persona**. Así variantes como
"Georg Friedrich Händel", "Handel George F." o "G. F. Handel" caen todas en la **misma**
persona, sin duplicar personas ni generar alias (el mismo nombre aparece muchas veces).

Uso:
    .venv\\Scripts\\python.exe scripts/link_import_by_identity.py --dry-run
    .venv\\Scripts\\python.exe scripts/link_import_by_identity.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

ROLE_COMPOSER = 1
ROLE_ARRANGER = 3
_ARR = re.compile(r"\s*[,;]?\s*(?:arr\.?|arranged|arrangement)\s*(?:by)?\s*[:.]?\s*", re.I)


def key(name: str) -> str:
    """Clave canónica sin acentos: iniciales + apellido."""
    t = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    t = t.lower().replace("'", "").replace("_", " ")
    toks = re.findall(r"[a-z]+", t)
    if not toks:
        return ""
    if len(toks) > 1 and toks[-2] == "o":
        return f"o{toks[-1]} {''.join(x[0] for x in toks[:-2])}".strip()
    return f"{''.join(x[0] for x in toks[:-1])} {toks[-1]}".strip()


async def run(db_name: str, dry_run: bool, roles: list[str]) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT identity_name, persons_id FROM persons_identity WHERE persons_id IS NOT NULL"
        )
        votes: dict[str, Counter] = {}
        for r in await cur.fetchall():
            k = key(str(r["identity_name"]))
            if k:
                votes.setdefault(k, Counter())[str(r["persons_id"])] += 1
        # Una persona por clave: la más votada (empate → determinista).
        by_key: dict[str, str] = {
            k: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for k, c in votes.items()
        }

        roles_ph = ", ".join(["%s"] * len(roles))
        await cur.execute(
            f"SELECT id, works_id, works_person_import_name AS name FROM works_person_import "
            f"WHERE works_person_import_resolved = 0 AND works_person_import_role IN ({roles_ph})",
            roles,
        )
        rows = await cur.fetchall()

    links: list[tuple[int, str, int]] = []
    resolved: list[int] = []
    stats = {"filas": len(rows), "resueltas": 0, "sin_match": 0, "arreglistas": 0}
    seen: set[tuple[int, str, int]] = set()

    for r in rows:
        raw = str(r["name"])
        role = ROLE_ARRANGER if _ARR.search(raw) else ROLE_COMPOSER
        base_name = _ARR.split(raw, maxsplit=1)[0] if role == ROLE_ARRANGER else raw
        k = key(base_name)
        pid = by_key.get(k)
        if not pid:
            stats["sin_match"] += 1
            continue
        tri = (int(r["works_id"]), pid, role)
        if tri not in seen:
            seen.add(tri)
            links.append(tri)
        resolved.append(int(r["id"]))
        stats["resueltas"] += 1
        if role == ROLE_ARRANGER:
            stats["arreglistas"] += 1

    print(stats, "| personas distintas:", len({p for _, p, _ in links}))

    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        if links:
            await cur.executemany(
                "INSERT IGNORE INTO works_person_roles (works_person_roles_work_id, "
                "works_person_roles_person_id, works_person_roles_role_id) VALUES (%s,%s,%s)",
                links,
            )
        for i in range(0, len(resolved), 1000):
            chunk = resolved[i : i + 1000]
            ph = ", ".join(["%s"] * len(chunk))
            await cur.execute(
                f"UPDATE works_person_import SET works_person_import_resolved = 1 "
                f"WHERE id IN ({ph})",
                chunk,
            )
    await db.close()
    print(f"relaciones: {len(links)} | marcadas: {len(resolved)}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--roles", default="composer,artist")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.db, args.dry_run, [r.strip() for r in args.roles.split(",") if r.strip()]))


if __name__ == "__main__":
    main()
