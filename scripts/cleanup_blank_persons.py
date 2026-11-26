"""Limpia personas con nombre vacío (o solo signos) y reasigna sus obras.

Causa: `resolve_persons.py` creaba una persona nueva para nombres de compositor
vacíos o formados solo por signos ("?", "- -"). En producción eso dejó 152 personas
ocultas sin nombre y 1.149 vínculos duplicados sobre 148 obras. El mantenimiento de
compositores las mostraba (visible=all) como 5 páginas de filas sin nombre.

Qué hace:
1. Detecta personas con nombre vacío (y opcionalmente sin ninguna letra).
2. Para cada obra afectada:
   - si tiene otro compositor válido, solo elimina el vínculo de la persona vacía;
   - si no, la vincula a `Compositor sin indicar` (UNKNOWN_PERSON_ID) y, si el tipo de
     atribución está vacío, lo marca como ANONIMA.
3. Elimina las personas vacías y sus vínculos.
4. Guarda un JSON de respaldo en `var/` antes de aplicar.

Uso:
    .venv\\Scripts\\python.exe scripts/cleanup_blank_persons.py
    .venv\\Scripts\\python.exe scripts/cleanup_blank_persons.py --apply
    # incluir también nombres sin letras (p. ej. "???") además de los vacíos:
    ... --include-punctuation --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.entities.composer import UNKNOWN_COMPOSER, UNKNOWN_COMPOSER_ID  # noqa: E402
from infrastructure.config import PROJECT_ROOT, Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_MAX_SAMPLE = 30


def _is_invalid_name(name: str, *, include_punctuation: bool) -> bool:
    text = (name or "").strip()
    if not text:
        return True
    return include_punctuation and not _LETTER_RE.search(text)


def _placeholders(count: int) -> str:
    return ", ".join(["%s"] * count)


async def run(db_name: str, *, apply: bool, include_punctuation: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    async with db.transaction() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT persons_id, persons_name, persons_visible, persons_source_system "
            "FROM persons WHERE persons_id <> %s",
            (UNKNOWN_COMPOSER_ID,),
        )
        candidates = [
            r for r in await cur.fetchall()
            if _is_invalid_name(r["persons_name"], include_punctuation=include_punctuation)
        ]
        if not candidates:
            print("No hay personas sin nombre que limpiar.")
            return

        ids = [r["persons_id"] for r in candidates]
        id_ph = _placeholders(len(ids))
        await cur.execute(
            "SELECT works_person_roles_person_id AS person_id, "
            "works_person_roles_work_id AS work_id, works_person_roles_role_id AS role_id "
            f"FROM works_person_roles WHERE works_person_roles_person_id IN ({id_ph})",
            ids,
        )
        links = await cur.fetchall()
        await cur.execute(
            f"SELECT * FROM persons_identity WHERE persons_id IN ({id_ph})", ids
        )
        identities = await cur.fetchall()
        await cur.execute(
            f"SELECT * FROM persons_evidence WHERE persons_id IN ({id_ph})", ids
        )
        evidence = await cur.fetchall()
        await cur.execute(f"SELECT * FROM persons_aliases WHERE person_id IN ({id_ph})", ids)
        aliases = await cur.fetchall()

        links_by_person: dict[str, list[dict[str, int]]] = {pid: [] for pid in ids}
        composer_works: set[int] = set()
        for link in links:
            links_by_person[link["person_id"]].append(
                {"work_id": int(link["work_id"]), "role_id": int(link["role_id"])}
            )
            if int(link["role_id"]) == 1:
                composer_works.add(int(link["work_id"]))

        valid_composer_works: set[int] = set()
        if composer_works:
            work_ids = sorted(composer_works)
            work_ph = _placeholders(len(work_ids))
            await cur.execute(
                "SELECT DISTINCT r.works_person_roles_work_id AS work_id "
                "FROM works_person_roles r JOIN persons p "
                "ON p.persons_id = r.works_person_roles_person_id "
                "WHERE r.works_person_roles_role_id = 1 "
                f"AND p.persons_id NOT IN ({id_ph}) "
                "AND CHAR_LENGTH(TRIM(p.persons_name)) > 0 "
                f"AND r.works_person_roles_work_id IN ({work_ph})",
                [*ids, *work_ids],
            )
            valid_composer_works = {int(r["work_id"]) for r in await cur.fetchall()}

        orphan_works = sorted(composer_works - valid_composer_works)
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "database": db_name,
            "applied": apply,
            "include_punctuation": include_punctuation,
            "unknown_person_id": UNKNOWN_COMPOSER_ID,
            "unknown_person_name": UNKNOWN_COMPOSER,
            "persons_count": len(candidates),
            "links_count": len(links),
            "works_with_blank_composer": len(composer_works),
            "works_only_blank_composer": len(orphan_works),
            "persons": [
                {
                    "id": r["persons_id"],
                    "name": r["persons_name"],
                    "visible": bool(r["persons_visible"]),
                    "source": r["persons_source_system"],
                    "links": links_by_person[r["persons_id"]],
                }
                for r in candidates
            ],
            "orphan_work_ids": orphan_works,
            "valid_composer_work_ids": sorted(valid_composer_works),
            "identities": identities,
            "evidence": evidence,
            "aliases": aliases,
        }
        backup_path = (
            PROJECT_ROOT / "var"
            / f"cleanup_blank_persons_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

        print({
            "personas_sin_nombre": len(candidates),
            "vinculos": len(links),
            "obras_con_compositor_vacio": len(composer_works),
            "obras_solo_compositor_vacio": len(orphan_works),
            "personas_muestra": [r["persons_id"] for r in candidates[:_MAX_SAMPLE]],
            "backup": str(backup_path),
        })
        if not apply:
            print("DRY-RUN: no se ha modificado la base de datos. Usa --apply para aplicar.")
            return

        await cur.execute(
            "INSERT IGNORE INTO persons "
            "(persons_id, persons_name, persons_visible, persons_source_system, persons_type) "
            "VALUES (%s, %s, 1, 'system', 'anonymous')",
            (UNKNOWN_COMPOSER_ID, UNKNOWN_COMPOSER),
        )
        if orphan_works:
            await cur.executemany(
                "INSERT IGNORE INTO works_person_roles "
                "(works_person_roles_work_id, works_person_roles_person_id, "
                "works_person_roles_role_id) VALUES (%s, %s, 1)",
                [(work_id, UNKNOWN_COMPOSER_ID) for work_id in orphan_works],
            )
            orphan_ph = _placeholders(len(orphan_works))
            await cur.execute(
                "UPDATE works SET works_attr_type = 'ANONIMA' "
                f"WHERE id IN ({orphan_ph}) "
                "AND (works_attr_type IS NULL OR TRIM(works_attr_type) = '')",
                orphan_works,
            )
        await cur.execute(
            f"DELETE FROM works_person_roles WHERE works_person_roles_person_id IN ({id_ph})",
            ids,
        )
        # persons_aliases no tiene FK declarada en producción: limpiar explícitamente.
        await cur.execute(f"DELETE FROM persons_aliases WHERE person_id IN ({id_ph})", ids)
        await cur.execute(f"DELETE FROM persons WHERE persons_id IN ({id_ph})", ids)

    await db.close()
    print("Limpieza aplicada correctamente.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap_storage")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Aplica los cambios (sin esta opción solo muestra el informe y el respaldo).",
    )
    ap.add_argument(
        "--include-punctuation",
        action="store_true",
        help="Incluye nombres no vacíos pero sin letras (p. ej. '???', '- -').",
    )
    args = ap.parse_args()
    asyncio.run(run(args.db, apply=args.apply, include_punctuation=args.include_punctuation))


if __name__ == "__main__":
    main()
