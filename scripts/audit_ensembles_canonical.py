#!/usr/bin/env python
"""Entiende la tabla `ensembles` aplicando la función canónica (read-only).

Canonicaliza cada `ensembles_code` con `domain.services.ensemble_canonical` y produce:
  - un CSV por fila: id_canonico, kind, family, voces, descripción y notas;
  - un CSV agrupado por id_canonico (alias que colapsan en la misma formación).

No escribe en la base de datos. Ver `docs/osap/ensemble-canonical-model.md`.

Uso (en osap-storage, con su venv y `PYTHONPATH=.`):
    python scripts/audit_ensembles_canonical.py
    python scripts/audit_ensembles_canonical.py --out output/ensembles_canonical.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from collections import Counter, defaultdict
from pathlib import Path

from domain.services.ensemble_canonical import VOICE_ORDER, canonical_ensemble
from infrastructure.config import Settings
from infrastructure.db.connection import Database


async def _read_rows() -> list[dict]:
    db = Database(Settings())  # type: ignore[call-arg]
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, ensembles_name, ensembles_code, ensembles_description "
            "FROM ensembles ORDER BY id"
        )
        return list(await cur.fetchall())


def _counts_txt(counts: dict[str, int]) -> str:
    return " ".join(f"{v}{counts[v]}" for v in VOICE_ORDER if counts.get(v, 0))


def run(out_path: Path, groups_path: Path) -> None:
    rows = asyncio.run(_read_rows())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    kinds: Counter[str] = Counter()
    changed = 0

    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "ensembles_id", "ensembles_code", "ensembles_name", "id_canonico",
            "kind", "family", "total_voces", "firma_frecuencias", "descripcion", "notas",
        ])
        for row in rows:
            code = str(row["ensembles_code"] or "")
            info = canonical_ensemble(code)
            if info.id_canonico != code:
                changed += 1
            kinds[info.kind] += 1
            groups[info.id_canonico].append((int(row["id"]), code))
            writer.writerow([
                row["id"], code, row["ensembles_name"], info.id_canonico,
                info.kind, info.family, info.total_voices,
                _counts_txt(dict(info.voice_counts)), info.description,
                "; ".join(info.notes),
            ])

    groups_path.parent.mkdir(parents=True, exist_ok=True)
    with groups_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id_canonico", "n_codigos", "ensembles_codes"])
        for id_canonico, items in sorted(groups.items(), key=lambda kv: (len(kv[1]), kv[0])):
            writer.writerow([id_canonico, len(items), " | ".join(c for _, c in items)])

    total = len(rows)
    print(f"filas                : {total}")
    print(f"codigo != id_canonico: {changed}")
    print(f"ids canonicos        : {len(groups)}")
    print("por kind             : " + ", ".join(f"{k}={v}" for k, v in kinds.most_common()))
    colisiones = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"ids con >1 alias     : {len(colisiones)}")
    print(f"escrito {out_path}")
    print(f"escrito {groups_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output/ensembles_canonical.csv")
    parser.add_argument("--groups", default="output/ensembles_canonical_groups.csv")
    args = parser.parse_args()
    run(Path(args.out), Path(args.groups))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
