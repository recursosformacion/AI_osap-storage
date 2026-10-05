"""Corrige entidades HTML mal renderizadas en textos de osap-storage (Dev/Prod).

`&NDASH`/`&ndash` -> `–` (en dash), `&TIMES`/`&times` -> `×`, `&amp;`/`&AMP;` -> `&`.
Solo decodifica entidades REALES (no toca ampersands normales). Read-only salvo `--apply`,
que toma snapshot en `output/` antes de escribir.

Uso:
    .venv\\Scripts\\python.exe scripts/fix_html_entities.py            # dry-run
    .venv\\Scripts\\python.exe scripts/fix_html_entities.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from infrastructure.config import Settings
from infrastructure.db.connection import Database

OUT = Path("output")

# (entidad, reemplazo). Orden: variantes con `;` antes que sin ella.
ENTIDADES: list[tuple[str, str]] = [
    ("&NDASH;", "–"), ("&NDASH", "–"), ("&ndash;", "–"), ("&ndash", "–"),
    ("&TIMES;", "×"), ("&TIMES", "×"), ("&times;", "×"), ("&times", "×"),
    ("&AMP;", "&"), ("&amp;", "&"),
]

COLUMNAS: list[tuple[str, str]] = [
    ("ensembles", "ensembles_code"),
    ("ensembles", "ensembles_name"),
    ("ensembles", "ensembles_description"),
    ("works", "works_title"),
    ("works", "works_description"),
    ("instruments", "name_es"),
    ("instruments", "name_en"),
    ("instrument_categories", "name"),
]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = Database(Settings())  # type: ignore[call-arg]
    plan: list[dict] = []
    async with db.connection() as conn, conn.cursor() as cur:
        for tabla, col in COLUMNAS:
            for ent, _rep in ENTIDADES:
                await cur.execute(
                    f"SELECT COUNT(*) AS n FROM `{tabla}` WHERE `{col}` LIKE %s", (f"%{ent}%",)
                )
                n = int((await cur.fetchone())["n"])
                if n:
                    plan.append({"tabla": tabla, "columna": col, "entidad": ent, "filas": n})

        resumen = sum(item["filas"] for item in plan)
        print(json.dumps({"cambios": len(plan), "filas_totales": resumen, "plan": plan},
                         ensure_ascii=False, indent=1))
        if not args.apply or not plan:
            if not args.apply:
                print("dry-run: no se escribe. Repetir con --apply.")
            return

        OUT.mkdir(parents=True, exist_ok=True)
        snapshot: dict[str, list[dict]] = {}
        for tabla, col in COLUMNAS:
            await cur.execute(
                f"SELECT `{col}` AS v FROM `{tabla}` WHERE `{col}` LIKE %s AND "
                f"(`{col}` LIKE '%%&NDASH%%' OR `{col}` LIKE '%%&ndash%%' OR `{col}` LIKE '%%&TIMES%%' "
                f"OR `{col}` LIKE '%%&times%%' OR `{col}` LIKE '%%&amp;%%' OR `{col}` LIKE '%%&AMP;%%')",
                ("%&%",),
            )
            snapshot[f"{tabla}.{col}"] = [str(r["v"]) for r in await cur.fetchall()]
        (OUT / "html_entities_snapshot.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8"
        )

        aplicado: list[dict] = []
        for tabla, col in COLUMNAS:
            for ent, rep in ENTIDADES:
                await cur.execute(
                    f"UPDATE `{tabla}` SET `{col}` = REPLACE(`{col}`, %s, %s) WHERE `{col}` LIKE %s",
                    (ent, rep, f"%{ent}%"),
                )
                if cur.rowcount:
                    aplicado.append({"tabla": tabla, "columna": col, "entidad": ent,
                                     "filas": int(cur.rowcount)})
    await db.close()
    (OUT / "html_entities_report.json").write_text(
        json.dumps({"aplicado": aplicado}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps({"aplicado": aplicado}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
