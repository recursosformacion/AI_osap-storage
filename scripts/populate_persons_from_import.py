"""Da de alta los compositores PDMX de `works_person_import` que no casan con nadie.

Cada fila de `works_person_import` corresponde a al menos una obra, así que el nombre es
de un compositor real. El problema son las variantes de escritura/iniciales, así que:

  1. Limpia y filtra ruido/mojibake (`domain.services.composer_quality`).
  2. Agrupa por **forma normalizada** del nombre (minúsculas, sin acentos ni puntuación).
  3. Elige el nombre canónico del grupo (el más frecuente; desempate el más largo).
  4. Si ya existe una persona (por `persons` o `persons_aliases`) se reutiliza; si no, se
     **crea** una persona (`source_system='pdmx'`) con ese nombre y su alias.
  5. Crea la fila en `works_person_roles` (rol 1) y marca `works_person_import_resolved = 1`
     para todas las filas del grupo.

Es idempotente: los grupos que ya existen no se duplican y las filas marcadas se saltan.

Uso:
    .venv\\Scripts\\python.exe scripts/populate_persons_from_import.py --dry-run
    .venv\\Scripts\\python.exe scripts/populate_persons_from_import.py --roles composer
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_names import normalize_composer_name  # noqa: E402
from domain.services.composer_quality import (  # noqa: E402
    clean_composer_name,
    is_mojibake,
)
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from link_works_person_import import ROLE_IDS, clean_raw, compact  # noqa: E402

SOURCE_SYSTEM = "pdmx"
_NOISE_TOKEN = re.compile(
    r"\b(urheber|unbekannt|unknown|anonymous|anonimo|trad|traditional|datum|quelle|"
    r"page|band|choir|chorus|group|ensemble|orchestra|tome|transkribierten|schriftlichen|"
    r"nach|after|attrib|attributed|arranged|arr|edition|editor|volume|vol|book|"
    r"various|composer)\b"
)
_EMPTY = {
    "na", "n a", "nan", "null", "none", "unknown", "desconocido", "anon", "anonimo",
    "anonymous", "trad", "tradicional", "traditional", "various", "attrib", "attributed",
    "composer", "unattributed", "gregorian chant", "-", "?", "s d", "sg", "o",
}


def is_personlike(name: str) -> bool:
    key = normalize_composer_name(name)
    if key in _EMPTY or len(key) < 4 or len(key) > 60:
        return False
    if any(ch.isdigit() for ch in key):
        return False
    if _NOISE_TOKEN.search(key):
        return False
    tokens = key.split()
    if len(tokens) > 6:
        return False
    # Todas las palabras deben ser alfabéticas (con apóstrofo/guion) y al menos una 3+ letras.
    if not all(re.fullmatch(r"[a-z][a-z'\-]*", t) for t in tokens):
        return False
    return any(len(t) >= 3 for t in tokens)


async def run(db_name: str, roles: list[str], dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    by_norm: dict[str, set[str]] = defaultdict(set)
    by_compact: dict[str, set[str]] = defaultdict(set)

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
        roles_ph = ", ".join(["%s"] * len(roles))
        await cur.execute(
            f"SELECT i.id, i.works_id, i.works_person_import_name AS name, "
            f"i.works_person_import_role AS role FROM works_person_import i "
            f"WHERE i.works_person_import_resolved = 0 "
            f"AND i.works_person_import_role IN ({roles_ph})",
            roles,
        )
        rows = await cur.fetchall()

    groups: dict[str, dict] = {}
    skipped = {"ruido": 0, "mojibake": 0, "no_persona": 0}
    for r in rows:
        raw = clean_raw(str(r["name"]))
        if is_mojibake(raw):
            skipped["mojibake"] += 1
            continue
        extracted = clean_composer_name(raw) or raw
        key = normalize_composer_name(extracted or "")
        if not key or key in _EMPTY:
            skipped["ruido"] += 1
            continue
        if not is_personlike(extracted):
            skipped["no_persona"] += 1
            continue
        g = groups.setdefault(key, {"spellings": defaultdict(int), "rows": []})
        g["spellings"][extracted] += 1
        g["rows"].append((int(r["id"]), int(r["works_id"]), str(r["role"])))

    existing = 0
    to_create: dict[str, dict] = {}
    for key, g in groups.items():
        canonical = min(g["spellings"].items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0]
        g["canonical"] = canonical
        if by_norm.get(key) or by_compact.get(compact(canonical)):
            existing += 1
        else:
            to_create[key] = g

    print(
        {
            "filas": len(rows),
            "grupos": len(groups),
            "grupos que ya existen": existing,
            "grupos a crear": len(to_create),
            "ruido": skipped["ruido"],
            "mojibake": skipped["mojibake"],
            "no_persona": skipped["no_persona"],
        }
    )
    print("muestra a crear:")
    for _key, g in sorted(to_create.items(), key=lambda kv: -sum(kv[1]["spellings"].values()))[:15]:
        print(f"  {sum(g['spellings'].values()):>5} obras  {g['canonical']}")
    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for key, g in to_create.items():
            canonical = g["canonical"]
            pid = str(uuid.uuid4())
            await cur.execute(
                "INSERT IGNORE INTO persons (persons_id, persons_name, persons_visible, "
                "persons_status, persons_source_system) VALUES (%s, %s, 1, 'active', %s)",
                (pid, canonical[:255], SOURCE_SYSTEM),
            )
            await cur.execute(
                "INSERT IGNORE INTO persons_aliases (person_id, person_aliases_alias, "
                "person_aliases_normalized_alias) VALUES (%s, %s, %s)",
                (pid, canonical[:255], normalize_composer_name(canonical)[:255]),
            )
            by_norm.setdefault(key, set()).add(pid)
        # Re-resuelve (grupos nuevos + existentes) y enlaza.
        links: list[tuple[int, str, int]] = []
        resolved: list[int] = []
        for key, g in groups.items():
            pids = by_norm.get(key) or by_compact.get(compact(g["canonical"])) or set()
            if len(pids) != 1:
                continue
            pid = next(iter(pids))
            for row_id, works_id, role in g["rows"]:
                links.append((works_id, pid, ROLE_IDS[role]))
                resolved.append(row_id)
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
    print(f"personas creadas: {len(to_create)} | relaciones: {len(links)} | "
          f"filas marcadas: {len(resolved)}")


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
