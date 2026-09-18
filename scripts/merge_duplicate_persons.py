"""Fusiona personas duplicadas del mismo compositor usando la clave de identidad.

Reglas (aprendidas del falso merge "Wilhelm/Wenzel Müller"):
  1. Se calcula una **clave limpia** por persona: sin acentos y quitando sufijos/ruido de
     nombre (paréntesis, años, tonalidades, catálogos Op./Nr., y frases de rol
     "by/from/arranger…").
  2. Sólo se agrupan personas con la **misma clave** y al menos **2 tokens** de nombre en
     común con el canónico del grupo.
  3. **Regla del apellido único**: un grupo cuyo canónico quedó reducido a una sola
     palabra (sólo apellido, p. ej. "from Handel" → "Handel") se fusiona en la familia
     con ese apellido, pero **sólo** si hay una familia clara y dominante (evita el caso
     "Müller", donde el apellido lo comparten muchos compositores distintos).
  4. El **canónico** del grupo se elige por prioridad de origen
     (`maestro` > `authority` > `web` > `identity-resolver` > `cpdl` > `pdmx`), luego el
     nombre más largo y, en empate, el `persons_id` menor.
  5. Se **reapunta todo** al canónico (`works_person_roles`, `persons_aliases`,
     `persons_identity`, `persons_evidence`) y se registra en `persons_merge_history`.
     **Nunca** se borran relaciones.
  6. Sólo se borra la persona duplicada.

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

_PRIORITY = {
    "maestro": 0,
    "authority": 1,
    "web": 2,
    "identity-resolver": 3,
    "cpdl": 4,
    "pdmx": 5,
    "": 9,
}
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


def words(name: str) -> list[str]:
    """Palabras del nombre limpio (para distinguir "Handel" de "G.F. Handel")."""
    return clean_name(name).lower().split()


def surname_token(name: str) -> str:
    parts = words(name)
    return re.sub(r"[^a-z]", "", parts[-1]) if parts else ""


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
        needle = fold(like).lower()
        if not needle:
            print(f"--like {like!r} no tiene caracteres comparables; se cancela el filtro.")
            await db.close()
            return
        persons = [p for p in persons if needle in fold(str(p["persons_name"])).lower()]

    groups: dict[str, list[dict]] = defaultdict(list)
    for p in persons:
        k = key(str(p["persons_name"]))
        if k:
            groups[k].append(p)

    for members in groups.values():
        members.sort(
            key=lambda p: (
                _PRIORITY.get(str(p["persons_source_system"] or "").lower(), 9),
                -len(str(p["persons_name"])),
                str(p["persons_id"]),
            )
        )

    def surname(name: str) -> str:
        return (clean_name(name).lower().split() or [""])[-1]

    # Separa los grupos "sólo apellido" (canónico de una sola palabra) de las familias
    # con nombre completo, y decide a qué familia cae cada apellido huérfano.
    named_by_surname: dict[str, list[str]] = defaultdict(list)
    bare: dict[str, list[dict]] = {}
    for k, members in groups.items():
        cname = str(members[0]["persons_name"])
        if len(words(cname)) == 1:
            bare[k] = members
        else:
            st = surname_token(cname)
            if st:
                named_by_surname[st].append(k)

    fold_target: dict[str, str] = {}
    for k, members in bare.items():
        st = surname_token(str(members[0]["persons_name"]))
        counts = {ck: len(groups[ck]) for ck in named_by_surname.get(st, [])}
        if not counts:
            continue
        top = max(counts, key=lambda ck: counts[ck])
        others = sum(v for ck, v in counts.items() if ck != top)
        # Sólo si la familia es clara y domina al resto (así "Müller" no se fusiona).
        if counts[top] >= 2 and counts[top] > others:
            fold_target[k] = top

    merges: dict[str, dict] = {}  # keeper_id -> {name, dups, motivos}

    def plan(keeper: dict, dups: list[dict], motivo: str) -> None:
        entry = merges.setdefault(
            str(keeper["persons_id"]),
            {"name": str(keeper["persons_name"]), "dups": set(), "motivos": set()},
        )
        entry["dups"].update(str(d["persons_id"]) for d in dups)
        entry["motivos"].add(motivo)

    for k, members in groups.items():
        keeper = members[0]
        kn = str(keeper["persons_name"])
        ksurname = surname(kn)
        if k in fold_target:
            plan(groups[fold_target[k]][0], members, f"apellido unico '{ksurname}'")
            continue
        if len(members) < 2:
            continue
        dups = []
        for m in members[1:]:
            mn = str(m["persons_name"])
            msurname = surname(mn)
            shared = len(tokens(kn) & tokens(mn))
            if msurname == ksurname and (shared >= 2 or similar(kn, mn) >= 0.85):
                dups.append(m)
        if dups:
            plan(keeper, dups, "misma clave")

    total_dups = sum(len(e["dups"]) for e in merges.values())
    print({"grupos con duplicados": len(merges), "personas a fusionar": total_dups})
    for e in list(merges.values())[:15]:
        print(f"   {e['name']}  <=  {len(e['dups'])} duplicados  [{'+'.join(sorted(e['motivos']))}]")

    folds = [e for e in merges.values() if any(m.startswith("apellido unico") for m in e["motivos"])]
    print(f"regla apellido unico: {len(folds)} familias")
    for e in folds:
        print(f"   [apellido] {e['name']}  <=  {len(e['dups'])} duplicados")

    if dry_run or not merges:
        if dry_run and like:
            for keeper_id, e in merges.items():
                ids = [keeper_id, *sorted(e["dups"])]
                print(f"  --- {e['name']} ({keeper_id}) [{'+'.join(sorted(e['motivos']))}]")
                async with db.connection() as conn, conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT persons_id, persons_name FROM persons "
                        f"WHERE persons_id IN ({','.join(['%s'] * len(ids))})",
                        ids,
                    )
                    for r in await cur.fetchall():
                        print(f"       {r['persons_id']}  {r['persons_name']}")
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for keeper_id, e in merges.items():
            dups = sorted(e["dups"])
            ph = ", ".join(["%s"] * len(dups))
            # 1) Relaciones obra↔persona (evitando duplicados work+rol).
            await cur.execute(
                f"UPDATE IGNORE works_person_roles SET works_person_roles_person_id = %s "
                f"WHERE works_person_roles_person_id IN ({ph})",
                [keeper_id, *dups],
            )
            await cur.execute(
                f"DELETE FROM works_person_roles WHERE works_person_roles_person_id IN ({ph})",
                dups,
            )
            # 2) Alias.
            await cur.execute(
                f"UPDATE IGNORE persons_aliases SET person_id = %s WHERE person_id IN ({ph})",
                [keeper_id, *dups],
            )
            await cur.execute(
                f"DELETE FROM persons_aliases WHERE person_id IN ({ph})", dups
            )
            # 3) Identidad.
            await cur.execute(
                f"UPDATE persons_identity SET persons_id = %s WHERE persons_id IN ({ph})",
                [keeper_id, *dups],
            )
            # 4) Evidencia.
            await cur.execute(
                f"UPDATE persons_evidence SET persons_id = %s WHERE persons_id IN ({ph})",
                [keeper_id, *dups],
            )
            # 5) Historial y borrado.
            for dup in dups:
                await cur.execute(
                    "INSERT INTO persons_merge_history (source_person_id, target_person_id, "
                    "merged_by) VALUES (%s, %s, 'merge_duplicate_persons')",
                    (dup, keeper_id),
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
