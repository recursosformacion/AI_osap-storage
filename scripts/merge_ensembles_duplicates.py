"""Fusiona ensembles duplicados INEQUÍVOCOS (variantes de formato) — Dev/Prod.

Alcance estricto: solo duplicados por **normalización conservadora** (espacios/guiones/
underscores fuera; `.` se preserva para multi-coro, así `SATB.SATB` ≠ `SATB`). Reapunta
`work_ensembles` al destino y **borra** el origen, todo en **una transacción**. No toca
`artifact_letter`, `other`, `html_entity`, ni formaciones vocal_notation distintas.

Antes de aplicar, guarda snapshots en `output/`. Si falla cualquier invariante → rollback.

Uso:
    .venv\\Scripts\\python.exe scripts/merge_ensembles_duplicates.py           # dry-run
    .venv\\Scripts\\python.exe scripts/merge_ensembles_duplicates.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from infrastructure.config import Settings
from infrastructure.db.connection import Database

OUT = Path("output")


def normalize(code: str) -> str:
    base = unicodedata.normalize("NFKC", code).strip().upper()
    base = re.sub(r"[^A-Z0-9.]", "", base)
    return re.sub(r"\.+", ".", base).strip(".")


async def _snapshot(db: Database) -> dict[str, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id, ensembles_code AS code, ensembles_name AS name FROM ensembles")
        ensembles = [dict(r) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT works_id, ensembles_id, work_ensembles_quantity AS q FROM work_ensembles"
        )
        links = [dict(r) for r in await cur.fetchall()]
    counts: dict[str, int] = defaultdict(int)
    for link in links:
        counts[str(link["ensembles_id"])] += 1
    (OUT / "ensembles_snapshot.json").write_text(
        json.dumps(ensembles, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "work_ensembles_snapshot.json").write_text(
        json.dumps(links, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "ensemble_counts_snapshot.json").write_text(
        json.dumps(counts, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "ensembles": str(OUT / "ensembles_snapshot.json"),
        "work_ensembles": str(OUT / "work_ensembles_snapshot.json"),
        "counts": str(OUT / "ensemble_counts_snapshot.json"),
    }


async def _load(db: Database):  # noqa: ANN201
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id, ensembles_code AS code FROM ensembles")
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.execute("SELECT works_id, ensembles_id FROM work_ensembles")
        links = [dict(r) for r in await cur.fetchall()]
    counts: dict[int, int] = defaultdict(int)
    works_of: dict[int, set[int]] = defaultdict(set)
    for link in links:
        counts[int(link["ensembles_id"])] += 1
        works_of[int(link["ensembles_id"])].add(int(link["works_id"]))
    return rows, counts, works_of


def build_map(rows: list[dict], counts: dict[int, int]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        r["norm"] = normalize(str(r["code"]))
        groups[r["norm"]].append(r)
    merges: list[dict] = []
    for norm, variants in groups.items():
        if len(variants) < 2 or not norm:
            continue
        ordered = sorted(variants, key=lambda v: (-counts[int(v["id"])], -len(str(v["code"])), int(v["id"])))
        keeper = ordered[0]
        for origin in ordered[1:]:
            merges.append({
                "norm": norm,
                "origin_id": int(origin["id"]), "origin_code": origin["code"],
                "dest_id": int(keeper["id"]), "dest_code": keeper["code"],
            })
    return merges


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = Database(Settings())  # type: ignore[call-arg]
    rows, counts, works_of = await _load(db)
    merges = build_map(rows, counts)
    total_works = len({w for ws in works_of.values() for w in ws})

    print(json.dumps({
        "elementos_a_fusionar": len(merges),
        "obras_destino_afectadas": sum(len(works_of[m["origin_id"]]) for m in merges),
        "trabajos_totales_unicos": total_works,
    }, ensure_ascii=False, indent=1))
    if not args.apply:
        print("dry-run: no se escribe. Repetir con --apply.")
        return
    if len(merges) != 35:
        raise SystemExit(f"ABORTADO: el mapa tiene {len(merges)} elementos, se esperaban 35")

    snapshots = await _snapshot(db)
    origins = [m["origin_id"] for m in merges]

    # Verificación previa del alcance de obras: por cada merge, antes = dest ∪ origin.
    expected_after: dict[int, set[int]] = {}
    for m in merges:
        expected_after[m["dest_id"]] = (
            expected_after.get(m["dest_id"], set(works_of[m["dest_id"]])) | works_of[m["origin_id"]]
        )
    async with db.transaction() as conn, conn.cursor() as cur:
        for m in merges:
            await cur.execute(
                "INSERT IGNORE INTO work_ensembles (works_id, ensembles_id, work_ensembles_quantity) "
                "SELECT works_id, %s, work_ensembles_quantity FROM work_ensembles WHERE ensembles_id = %s",
                (m["dest_id"], m["origin_id"]),
            )
            await cur.execute("DELETE FROM work_ensembles WHERE ensembles_id = %s", (m["origin_id"],))
            await cur.execute("DELETE FROM ensembles WHERE id = %s", (m["origin_id"],))

        # --- invariantes DENTRO de la transacción (si fallan → rollback) ---
        await cur.execute(
            "SELECT COUNT(*) AS n FROM work_ensembles WHERE ensembles_id IN ("
            + ",".join(["%s"] * len(origins)) + ")", origins,
        )
        huerfanas = int((await cur.fetchone())["n"])
        await cur.execute("SELECT COUNT(*) AS n FROM work_ensembles")
        total_links = int((await cur.fetchone())["n"])
        await cur.execute("SELECT id, ensembles_code AS code FROM ensembles")
        rows_after = [dict(r) for r in await cur.fetchall()]
        await cur.execute("SELECT works_id, ensembles_id FROM work_ensembles")
        links_after = [dict(r) for r in await cur.fetchall()]

        works_after_all = {int(link["works_id"]) for link in links_after}
        por_ens: dict[int, set[int]] = defaultdict(set)
        for link in links_after:
            por_ens[int(link["ensembles_id"])].add(int(link["works_id"]))

        normas_antes = {normalize(str(r["code"])) for r in rows}
        normas_despues = {normalize(str(r["code"])) for r in rows_after}

        fallos: list[str] = []
        if huerfanas != 0:
            fallos.append(f"referencias huérfanas a orígenes: {huerfanas}")
        if len(works_after_all) != total_works:
            fallos.append(f"obras únicas cambiaron: {total_works} -> {len(works_after_all)}")
        for m in merges:
            if por_ens[m["origin_id"]]:
                fallos.append(f"origen {m['origin_code']} sigue con referencias")
            if por_ens[m["dest_id"]] != expected_after[m["dest_id"]]:
                fallos.append(
                    f"destino {m['dest_code']}: obras {len(por_ens[m['dest_id']])} != "
                    f"esperadas {len(expected_after[m['dest_id']])}"
                )
        if normas_antes != normas_despues:
            perdidas = normas_antes - normas_despues
            fallos.append(f"formaciones normalizadas perdidas: {sorted(perdidas)[:10]}")
        grupos_dup = [norm for norm, n in
                      ((k, len(v)) for k, v in _group_by_norm(rows_after).items()) if n > 1]
        if grupos_dup:
            fallos.append(f"duplicados nuevos: {grupos_dup[:10]}")

        if fallos:
            raise SystemExit("ROLLBACK: " + " | ".join(fallos))

    # --- informe (fuera de la transacción; ya commiteado) ---
    eliminados = [
        {"origen": m["origin_code"], "destino": m["dest_code"],
         "obras": len(works_of[m["origin_id"]]), "works_ids": sorted(works_of[m["origin_id"]])}
        for m in merges
    ]
    informe = {
        "snapshots": snapshots,
        "eliminados": eliminados,
        "eliminados_n": len(eliminados),
        "obras_afectadas": len({w for m in merges for w in works_of[m["origin_id"]]}),
        "work_ensembles_antes": sum(counts.values()),
        "work_ensembles_despues": total_links,
        "conservados": {"vocal_notation": 425, "artifact_letter": 26, "other": 22, "html_entity": 6},
    }
    (OUT / "ensembles_merge_report.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps({k: informe[k] for k in
                      ("eliminados_n", "obras_afectadas", "work_ensembles_antes",
                       "work_ensembles_despues")}, ensure_ascii=False, indent=1))
    await db.close()


def _group_by_norm(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[normalize(str(r["code"]))].append(r)
    return groups


if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
