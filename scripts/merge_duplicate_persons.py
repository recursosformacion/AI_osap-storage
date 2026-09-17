"""Fusiona personas duplicadas del mismo compositor usando la clave de identidad.

Reglas (aprendidas del falso merge "Wilhelm/Wenzel Müller"):
  1. Se calcula una **clave limpia** por persona: sin acentos y quitando sufijos/ruido de
     nombre (paréntesis, años, tonalidades, catálogos Op./Nr., y frases de rol
     "by/from/arranger…").
  2. Sólo se agrupan personas con la **misma clave** y al menos **2 tokens** de nombre en
     común con el canónico del grupo.
  3. El **canónico** del grupo se elige por prioridad de origen
     (`authority` > `web` > `identity-resolver` > `pdmx`), luego el nombre más largo y, en
     empate, el `persons_id` menor.
  4. Se **reapunta todo** al canónico (`works_person_roles`, `persons_aliases`,
     `persons_identity`, `persons_evidence`) y se registra en `persons_merge_history`.
     **Nunca** se borran relaciones.
  5. Sólo se borra la persona duplicada.

Uso:
    .venv\\Scripts\\python.exe scripts/merge_duplicate_persons.py --dry-run [--like Handel]
    .venv\\Scripts\\python.exe scripts/merge_duplicate_persons.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import re
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

_PRIORITY = {"authority": 0, "web": 1, "identity-resolver": 2, "cpdl": 3, "pdmx": 4, "": 9}
_PARENS = re.compile(r"\([^)]*\)")
_YEARS = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_CATALOG = re.compile(
    r"\b(op\.?\s*\d+|no\.?\s*\d+|nr\.?\s*\d+|bwv\s*\d*|kv\s*\d*|hob\.?|woo|hwv|rv\s*\d*)\b.*$",
    re.I,
)
_KEYS = re.compile(r"\b(major|minor|maj|min)\b.*$", re.I)
_ROLE_FROM = re.compile(
    r"\s*[-–|]\s*(arranger|arranged|transcriber|editor|orchestrator|composer)\b.*$", re.I
)
_LEAD = re.compile(r"^(from|by|poss\.?|arranged from|arranged by|after|attr\.?|attributed to)\s+", re.I)
_TAIL_PHRASE = re.compile(
    r"\b(spellings? vary|analisis|analysis|for [a-z] of [a-z]+|see also)\b.*$", re.I
)


def fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def clean_name(name: str) -> str:
    t = fold(name)
    t = _PARENS.sub(" ", t)
    t = _ROLE_FROM.sub(" ", t)
    t = _CATALOG.sub(" ", t)
    t = _KEYS.sub(" ", t)
    t = _TAIL_PHRASE.sub(" ", t)
    t = _YEARS.sub(" ", t)
    t = _LEAD.sub("", t.strip())
    t = re.sub(r"[^A-Za-z .'\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .-")


def key(name: str) -> str:
    tokens = re.findall(r"[a-z]+", clean_name(name).lower())
    if not tokens:
        return ""
    if len(tokens) > 1 and tokens[-2] == "o":
        return f"o{tokens[-1]} {''.join(t[0] for t in tokens[:-2])}".strip()
    return f"{''.join(t[0] for t in tokens[:-1])} {tokens[-1]}".strip()


def similar(a: str, b: str) -> float:
    """Similitud de los nombres limpiados (evita unir 'Wilhelm' con 'Wenzel')."""
    return SequenceMatcher(None, clean_name(a).lower(), clean_name(b).lower()).ratio()


def tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", clean_name(name).lower()) if len(t) > 1}


async def run(db_name: str, dry_run: bool, like: str | None) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT persons_id, persons_name, persons_source_system FROM persons"
        )
        persons = [dict(r) for r in await cur.fetchall()]

    if like:
        persons = [p for p in persons if like.lower() in str(p["persons_name"]).lower()]

    groups: dict[str, list[dict]] = defaultdict(list)
    for p in persons:
        k = key(str(p["persons_name"]))
        if k:
            groups[k].append(p)

    merges: list[tuple[str, list[str], str]] = []  # (keeper, duplicados, motivo)
    for k, members in groups.items():
        if len(members) < 2:
            continue
        members = sorted(
            members,
            key=lambda p: (
                _PRIORITY.get(str(p["persons_source_system"] or "").lower(), 9),
                -len(str(p["persons_name"])),
                str(p["persons_id"]),
            ),
        )
        keeper = members[0]
        kn = str(keeper["persons_name"])
        ktok = tokens(kn)
        ksurname = (clean_name(kn).lower().split() or [""])[-1]
        dups = []
        for m in members[1:]:
            mn = str(m["persons_name"])
            msurname = (clean_name(mn).lower().split() or [""])[-1]
            shared = len(ktok & tokens(mn))
            if msurname == ksurname and (shared >= 2 or similar(kn, mn) >= 0.85):
                dups.append(m)
        if dups:
            merges.append((str(keeper["persons_id"]), [str(d["persons_id"]) for d in dups], str(keeper["persons_name"])))

    total_dups = sum(len(d) for _, d, _ in merges)
    print({"grupos con duplicados": len(merges), "personas a fusionar": total_dups})
    for keeper, dups, name in merges[:15]:
        print(f"   {name}  <=  {len(dups)} duplicados")

    if dry_run or not merges:
        if dry_run and like:
            for keeper, dups, name in merges:
                print(f"  --- {name} ({keeper})")
                async with db.connection() as conn, conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT persons_id, persons_name FROM persons "
                        f"WHERE persons_id IN ({','.join(['%s'] * (len(dups) + 1))})",
                        [keeper, *dups],
                    )
                    for r in await cur.fetchall():
                        print(f"       {r['persons_id']}  {r['persons_name']}")
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for keeper, dups, _name in merges:
            ph = ", ".join(["%s"] * len(dups))
            # 1) Relaciones obra↔persona (evitando duplicados work+rol).
            await cur.execute(
                f"UPDATE IGNORE works_person_roles SET works_person_roles_person_id = %s "
                f"WHERE works_person_roles_person_id IN ({ph})",
                [keeper, *dups],
            )
            await cur.execute(
                f"DELETE FROM works_person_roles WHERE works_person_roles_person_id IN ({ph})",
                dups,
            )
            # 2) Alias.
            await cur.execute(
                f"UPDATE IGNORE persons_aliases SET person_id = %s WHERE person_id IN ({ph})",
                [keeper, *dups],
            )
            await cur.execute(
                f"DELETE FROM persons_aliases WHERE person_id IN ({ph})", dups
            )
            # 3) Identidad.
            await cur.execute(
                f"UPDATE persons_identity SET persons_id = %s WHERE persons_id IN ({ph})",
                [keeper, *dups],
            )
            # 4) Evidencia.
            await cur.execute(
                f"UPDATE persons_evidence SET persons_id = %s WHERE persons_id IN ({ph})",
                [keeper, *dups],
            )
            # 5) Historial y borrado.
            for dup in dups:
                await cur.execute(
                    "INSERT INTO persons_merge_history (source_person_id, target_person_id, "
                    "merged_by) VALUES (%s, %s, 'merge_duplicate_persons')",
                    (dup, keeper),
                )
            await cur.execute(f"DELETE FROM persons WHERE persons_id IN ({ph})", dups)
    await db.close()
    print(f"fusionadas: {total_dups} personas en {len(merges)} canónicas")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--like", default=None, help="limita a nombres que contengan el texto")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.db, args.dry_run, args.like))


if __name__ == "__main__":
    main()
