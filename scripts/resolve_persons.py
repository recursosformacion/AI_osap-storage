"""Resuelve los nombres de `works_person_import` (rol `composer`) a `persons` y crea
las relaciones `works_person_roles` (rol 1 = Composer).

Estrategia de resolución, por nombre:
1) `persons.persons_name` (normalizado)
2) `persons_aliases` (alias normalizado)
3) autoridad/candidatos en `persons_identity` (fila ancla, `identity_is_anchor = 1`): si el
   candidato ya está enlazado a una persona (`persons_id`) se usa; si no, se crea la persona
   con su `identity_name` y se enlazan sus filas marcándoles `persons_id`.
4) si no hay coincidencia, se crea una persona nueva con el nombre original.

Los artistas (rol `artist`) NO se resuelven aquí: se quedan en staging.

Uso:
    .venv\\Scripts\\python.exe scripts/resolve_persons.py --db osap-storage [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import unicodedata
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

_ANON = {
    "anon", "anon.", "anonymous", "trad", "trad.", "traditional", "attrib.", "attributed",
    "attrib", "unknown", "author unknown", "urheber unbekannt", "urheber unbek.",
}


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    t = t.lower().strip().replace("'", "").replace("\u2019", "")
    return re.sub(r"\s+", " ", t)


def clean_name(raw: str) -> str:
    t = (raw or "").strip()
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\s+\d{3,4}\s*$", "", t)
    return re.sub(r"\s+", " ", t).strip()


def composer_key(raw: str) -> str:
    """Clave canónica igual que la usada al cargar la autoridad (initials + apellido)."""
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


async def run(db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    tgt = Database(base.model_copy(update={"db_name": db_name}))
    await tgt.connect()

    async with tgt.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT persons_id, persons_name, persons_source_system FROM persons")
        by_norm: dict[str, str] = {}
        created: list[tuple[str, str, str]] = []  # nuevos
        for r in await cur.fetchall():
            by_norm.setdefault(norm(r["persons_name"]), r["persons_id"])

        await cur.execute("SELECT person_id, person_aliases_alias FROM persons_aliases")
        for r in await cur.fetchall():
            by_norm.setdefault(norm(r["person_aliases_alias"]), r["person_id"])

        # Autoridad/candidatos: en la identidad fusionada la fila ancla (`identity_is_anchor=1`)
        # guarda el nombre canónico y su `identity_name_norm`; `persons_id` NULL = candidato.
        await cur.execute(
            "SELECT identity_name, identity_name_norm, persons_id FROM persons_identity "
            "WHERE identity_is_anchor = 1"
        )
        auth_key: dict[str, tuple[str, str | None]] = {}
        for r in await cur.fetchall():
            k = str(r["identity_name_norm"] or "")
            if k:
                auth_key.setdefault(k, (str(r["identity_name"]), r["persons_id"]))

        await cur.execute(
            "SELECT works_id, works_person_import_name, works_person_import_source "
            "FROM works_person_import WHERE works_person_import_role = 'composer'"
        )
        rows = await cur.fetchall()

    # Resolución (cache por clave)
    resolved: list[tuple[int, str]] = []
    cache: dict[str, str] = {}
    stats = {"personas_existentes": 0, "autoridad": 0, "autoridad_nueva": 0, "nuevas": 0}
    auth_to_link: list[tuple[str, str]] = []

    for r in rows:
        wid = int(r["works_id"])
        raw = str(r["works_person_import_name"]).strip()
        key = norm(clean_name(raw)) or norm(raw)
        pid = cache.get(key)
        if pid is None:
            pid = by_norm.get(key)
            if pid:
                stats["personas_existentes"] += 1
            else:
                akey = composer_key(raw)
                auth = auth_key.get(akey)
                if auth is not None:
                    cname, linked = auth
                    if linked:
                        pid = linked
                        stats["autoridad"] += 1
                    else:
                        ckey = norm(cname)
                        pid = by_norm.get(ckey)
                        if pid is None:
                            pid = str(uuid.uuid4())
                            created.append((pid, cname, "resolved"))
                            by_norm[ckey] = pid
                            stats["autoridad_nueva"] += 1
                            auth_to_link.append((akey, pid))
                        else:
                            stats["personas_existentes"] += 1
                else:
                    pid = str(uuid.uuid4())
                    created.append((pid, clean_name(raw) or raw, "resolved"))
                    by_norm[key] = pid
                    stats["nuevas"] += 1
            cache[key] = pid
        resolved.append((wid, pid))

    print({"works composer": len(resolved), "personas nuevas": len(created), **stats})

    if dry_run:
        await tgt.close()
        return

    async with tgt.transaction() as conn, conn.cursor() as cur:
        if created:
            await cur.executemany(
                "INSERT IGNORE INTO persons (persons_id, persons_name, persons_source_system) "
                "VALUES (%s,%s,%s)",
                created,
            )
        for akey, pid in auth_to_link:
            await cur.execute(
                "UPDATE persons_identity SET persons_id=%s "
                "WHERE identity_name_norm=%s AND persons_id IS NULL",
                (pid, akey),
            )
        if resolved:
            await cur.executemany(
                "INSERT IGNORE INTO works_person_roles (works_person_roles_work_id, "
                "works_person_roles_person_id, works_person_roles_role_id) VALUES (%s,%s,1)",
                resolved,
            )
    await tgt.close()
    print("resolución completada")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.db, args.dry_run))


if __name__ == "__main__":
    main()
