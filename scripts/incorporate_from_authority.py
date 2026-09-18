"""Incorpora compositores desde `works_person_import` con la autoridad como respaldo.

Para cada fila pendiente (rol `composer` por defecto):
  1. Busca la persona por nombre normalizado/compacto en `persons` + `persons_aliases`.
  2. Si no la encuentra, la busca en la autoridad (`persons_identity`, candidatos con
     `persons_id` NULL) **por nombre completo normalizado** (no por clave: la clave
     iniciales+apellido da falsos positivos) y, si coincide, **da de alta la persona** con
     el nombre canónico y sus identificadores (`wikidata`/`viaf`/`imslp`), enlazándola con
     el candidato (poniéndole `persons_id` a sus filas).
  3. En ambos casos **crea la fila en `works_person_roles`** (rol 1 = Composer) y **marca
     la fila de `works_person_import` como asignada** (`works_person_import_resolved = 1`).

Lo que no casa con persona ni con la autoridad queda pendiente (no se inventa nada).

Uso:
    .venv\\Scripts\\python.exe scripts/incorporate_from_authority.py --dry-run
    .venv\\Scripts\\python.exe scripts/incorporate_from_authority.py --roles composer
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_names import normalize_composer_name  # noqa: E402
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from link_works_person_import import ROLE_IDS, clean_raw, compact, composer_key  # noqa: E402

SOURCE_SYSTEM = "authority"


async def run(db_name: str, roles: list[str], dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    by_norm: dict[str, set[str]] = defaultdict(set)
    by_compact: dict[str, set[str]] = defaultdict(set)
    work_count: dict[str, int] = {}
    authority: dict[str, dict] = {}

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT persons_id, persons_name FROM persons")
        for r in await cur.fetchall():
            by_norm[normalize_composer_name(r["persons_name"])].add(r["persons_id"])
            by_compact[compact(r["persons_name"])].add(r["persons_id"])
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

        # Autoridad/candidatos en `persons_identity`: la fila ancla guarda el nombre canónico;
        # los identificadores (wikidata/viaf/imslp) comparten su `identity_name_norm`.
        await cur.execute(
            "SELECT identity_name, identity_name_norm, identity_type, identity_value, "
            "identity_is_anchor FROM persons_identity"
        )
        auth_rows = await cur.fetchall()
        by_identity_norm: dict[str, str] = {}
        for r in auth_rows:
            if int(r["identity_is_anchor"]) == 1:
                key = normalize_composer_name(r["identity_name"])
                if key:
                    authority.setdefault(key, {
                        "name": str(r["identity_name"]),
                        "wikidata_id": None, "viaf_id": None, "imslp_id": None,
                        "identity_norm": str(r["identity_name_norm"] or ""),
                    })
                    by_identity_norm[str(r["identity_name_norm"] or "")] = key
        for r in auth_rows:
            itype = str(r["identity_type"] or "")
            if not itype:
                continue
            key = by_identity_norm.get(str(r["identity_name_norm"] or ""))
            field = {"wikidata_qid": "wikidata_id", "viaf": "viaf_id",
                     "imslp": "imslp_id"}.get(itype)
            if key and field and key in authority:
                authority[key][field] = r["identity_value"]

        roles_ph = ", ".join(["%s"] * len(roles))
        await cur.execute(
            f"SELECT id, works_id, works_person_import_name AS name, "
            f"works_person_import_role AS role FROM works_person_import "
            f"WHERE works_person_import_resolved = 0 "
            f"AND works_person_import_role IN ({roles_ph})",
            roles,
        )
        rows = await cur.fetchall()

    new_persons: list[tuple[str, str, dict]] = []  # (uuid, name, authority row)
    links: list[tuple[int, str, int]] = []
    resolved_ids: list[int] = []
    stats = {"rows": len(rows), "enlazadas": 0, "creadas": 0, "sin_match": 0, "ruido": 0}
    cache: dict[str, str | None] = {}

    def _best(candidates: set[str]) -> str | None:
        ranked = sorted(candidates, key=lambda p: (-work_count.get(p, 0), p))
        if len(ranked) == 1:
            return ranked[0]
        if work_count.get(ranked[0], 0) > work_count.get(ranked[1], 0):
            return ranked[0]
        return None

    for r in rows:
        raw = clean_raw(str(r["name"]))
        role_id = ROLE_IDS.get(str(r["role"]))
        if role_id is None:
            continue
        key = normalize_composer_name(raw)
        if not key:
            stats["ruido"] += 1
            continue
        pid = cache.get(key)
        fresh = key not in cache
        if fresh:
            candidates = by_norm.get(key) or by_compact.get(compact(raw)) or set()
            pid = _best(candidates) if candidates else None
            if pid is None and key in authority:
                auth = authority[key]
                name = str(auth["name"])
                pid = str(uuid.uuid4())
                new_persons.append((pid, name, dict(auth)))
                by_norm.setdefault(key, set()).add(pid)
                authority.pop(key)
                stats["creadas"] += 1
                cache[key] = pid
                links.append((int(r["works_id"]), pid, role_id))
                resolved_ids.append(int(r["id"]))
                continue
            cache[key] = pid
        if pid:
            if fresh:
                stats["enlazadas"] += 1
            links.append((int(r["works_id"]), pid, role_id))
            resolved_ids.append(int(r["id"]))
        else:
            stats["sin_match"] += 1

    print(stats, "| personas nuevas:", len(new_persons))

    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for pid, name, auth in new_persons:
            await cur.execute(
                "INSERT IGNORE INTO persons (persons_id, persons_name, persons_visible, "
                "persons_status, persons_source_system) "
                "VALUES (%s, %s, 1, 'active', %s)",
                (pid, name, SOURCE_SYSTEM),
            )
            for id_type, value in (
                ("wikidata_qid", auth.get("wikidata_id")),
                ("viaf", auth.get("viaf_id")),
                ("imslp", auth.get("imslp_id")),
            ):
                if value:
                    await cur.execute(
                        "INSERT INTO persons_identity "
                        "(persons_id, identity_name, identity_name_norm, identity_type, "
                        " identity_value, identity_source, identity_is_anchor) "
                        "VALUES (%s, %s, %s, %s, %s, 'authority', 0)",
                        (pid, name[:255], composer_key(name)[:128], id_type, str(value)),
                    )
            if auth.get("identity_norm"):
                await cur.execute(
                    "UPDATE persons_identity SET persons_id = %s "
                    "WHERE identity_name_norm = %s AND persons_id IS NULL",
                    (pid, auth["identity_norm"]),
                )
        if links:
            await cur.executemany(
                "INSERT IGNORE INTO works_person_roles "
                "(works_person_roles_work_id, works_person_roles_person_id, "
                " works_person_roles_role_id) VALUES (%s, %s, %s)",
                links,
            )
        for i in range(0, len(resolved_ids), 1000):
            chunk = resolved_ids[i : i + 1000]
            ph = ", ".join(["%s"] * len(chunk))
            await cur.execute(
                f"UPDATE works_person_import SET works_person_import_resolved = 1 "
                f"WHERE id IN ({ph})",
                chunk,
            )
    await db.close()
    print(
        f"personas nuevas: {len(new_persons)} | relaciones: {len(links)} | "
        f"filas marcadas: {len(resolved_ids)}"
    )


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--roles", default="composer")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    asyncio.run(run(args.db, roles, args.dry_run))


if __name__ == "__main__":
    main()
