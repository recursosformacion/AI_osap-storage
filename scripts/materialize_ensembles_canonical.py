#!/usr/bin/env python
"""Materializa el catálogo canónico de `ensembles` a partir de `canonical_ensemble`.

Planificador **read-only** (por defecto). Construye, sin escribir en BD:
  - una fila canónica por `id_canonico` (`ensembles_code = id_canonico`);
  - `ensembles_aliases` para cada código actual != su id canónico;
  - la reconstrucción de `ensemble_voices` desde la interpretación canónica;
  - el plan de repunte de `work_ensembles` antes de borrar los no canónicos.

Reglas de construcción (resueltas explícitamente, NO se derivan del id a ciegas):

  ensemble_voices:
    - kind VOICES  -> descomposición de `voice_counts` (agregado; incluye solistas) en el
      orden S, MZ, A, CT, T, BAR, B, mapeada al catálogo `voices`.
    - UNISON[_MOD] -> [Voice x1]; TREBLE -> [Treble x1]; DESCANT -> [Soprano x1].
    - CHILDREN, roles, SOLI_GROUP, INSTRUMENTAL_* y los centinelas -> sin filas (la
      semántica va en `ensembles_code`/description; no se inventa una formación).

  name:
    - si ya existe una fila cuyo `ensembles_code == id_canonico` -> se conserva su nombre;
    - si no -> se genera (familia + nº de voces + bloques; etiqueta para especiales).

  description:
    - si la fila canónica existente ya trae descripción no vacía -> se conserva;
    - si no -> la descripción reconstruida por `canonical_ensemble`.

Uso (osap-storage, venv, `PYTHONPATH=.`):
    python scripts/materialize_ensembles_canonical.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from collections import defaultdict
from pathlib import Path

from domain.services.ensemble_canonical import (
    VOICE_ORDER,
    CanonicalEnsemble,
    canonical_ensemble,
)
from infrastructure.config import Settings
from infrastructure.db.connection import Database

SYMBOL_VOICE_NAME = {
    "S": "Soprano",
    "MZ": "Mezzo-soprano",
    "A": "Contralto",
    "CT": "Countertenor",
    "T": "Tenor",
    "BAR": "Baritone",
    "B": "Bass",
}
_FAMILY_LABEL = {"MIXED": "Coro mixto", "FEMALE": "Coro femenino", "MALE": "Coro masculino"}
_LABEL = {
    "CHILDREN": "Coro infantil",
    "TREBLE": "Voces blancas (treble)",
    "DESCANT": "Descant (soprano solista)",
    "SOLI_GROUP": "Grupo solista",
    "UNSPECIFIED": "Sin formación concreta",
    "UNKNOWN": "Formación no interpretable",
    "INVALID_OR_INSTRUMENTAL": "No vocal / instrumental",
}
OUT_DIR = Path("output/ensembles_materialization")


def voices_for(info: CanonicalEnsemble) -> list[tuple[str, int]]:
    idc = info.id_canonico
    if info.kind == "VOICES":
        return [
            (SYMBOL_VOICE_NAME[v], info.voice_counts[v])
            for v in VOICE_ORDER
            if info.voice_counts.get(v, 0) > 0
        ]
    if idc.startswith("UNISON"):
        return [("Voice", 1)]
    if idc == "TREBLE":
        return [("Treble", 1)]
    if idc == "DESCANT":
        return [("Soprano", 1)]
    return []


def _voice_names(info: CanonicalEnsemble) -> str:
    return ", ".join(
        SYMBOL_VOICE_NAME[v] for v in VOICE_ORDER if info.voice_counts.get(v, 0) > 0
    )


def gen_name(info: CanonicalEnsemble) -> str:
    idc = info.id_canonico
    if info.kind == "VOICES":
        names = _voice_names(info)
        if info.total_voices <= 1:
            label = "Voz solista" if "SOLO" in idc else "Voz"
            return f"{label}: {names}" if names else label
        fam = _FAMILY_LABEL.get(info.family, "Conjunto vocal")
        name = f"{fam} a {info.total_voices} voces"
        if len(info.segments) > 1:
            name += f" ({len(info.segments)} bloques)"
        if "_SOLO_" in idc:
            name += " con solista"
        return name
    if idc.startswith("UNISON"):
        mod = idc[len("UNISON"):].strip("_").replace("_", " ").title()
        return f"Unísono {mod}".strip()
    return _LABEL.get(idc, info.description)


def _coherent_name(name: str, code: str) -> bool:
    """Un nombre solo se conserva si no es vacío ni es el propio código."""
    clean = name.strip()
    return bool(clean) and clean.upper() != code.upper()


async def _load() -> tuple[list[dict], dict[str, int]]:
    db = Database(Settings())  # type: ignore[call-arg]
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id, voices_name FROM voices")
        voice_ids = {str(r["voices_name"]): int(r["id"]) for r in await cur.fetchall()}
        await cur.execute(
            "SELECT id, ensembles_name, ensembles_code, ensembles_description "
            "FROM ensembles ORDER BY id"
        )
        rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return rows, voice_ids


def plan() -> dict:
    rows, voice_ids = asyncio.run(_load())
    by_code = {str(r["ensembles_code"] or ""): r for r in rows}

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        info = canonical_ensemble(str(row["ensembles_code"] or ""))
        groups[info.id_canonico].append({"row": row, "info": info})

    canonical_rows: list[dict] = []
    aliases: list[dict] = []
    repoints: list[dict] = []

    for id_canonico, items in sorted(groups.items()):
        existing = by_code.get(id_canonico)
        info = canonical_ensemble(id_canonico)
        # name / description
        if existing is not None:
            raw_name = str(existing["ensembles_name"] or "").strip()
            name = raw_name if _coherent_name(raw_name, id_canonico) else gen_name(info)
            desc = str(existing["ensembles_description"] or "").strip() or info.description
        else:
            name = gen_name(info)
            desc = info.description
        voices = voices_for(info)
        canonical_rows.append({
            "id_canonico": id_canonico,
            "existing_ensembles_id": existing["id"] if existing else "",
            "kind": info.kind,
            "family": info.family,
            "name": name,
            "description": desc,
            "voices": " ".join(f"{v}×{q}" for v, q in voices),
        })
        for it in items:
            raw_id = int(it["row"]["id"])
            raw_code = str(it["row"]["ensembles_code"] or "")
            if raw_code != id_canonico:
                aliases.append({"raw_code": raw_code, "id_canonico": id_canonico,
                                "raw_ensembles_id": raw_id})
                repoints.append({"raw_ensembles_id": raw_id, "to_id_canonico": id_canonico})

    # invariant: no original lost
    original = {str(r["ensembles_code"] or "") for r in rows}
    covered = {r["id_canonico"] for r in canonical_rows} | {a["raw_code"] for a in aliases}
    missing = original - covered
    alias_targets = {r["id_canonico"] for r in canonical_rows}
    bad_alias = [a for a in aliases if a["id_canonico"] not in alias_targets]
    voice_missing = [
        r for r in canonical_rows if r["kind"] == "VOICES" and not r["voices"]
    ]

    return {
        "original_rows": len(rows),
        "canonical_ids": len(groups),
        "new_rows": sum(1 for r in canonical_rows if r["existing_ensembles_id"] == ""),
        "aliases": len(aliases),
        "groups_with_alias": sum(1 for g in groups.values() if len(g) > 1),
        "missing_original": sorted(missing),
        "bad_alias": bad_alias,
        "voice_missing": voice_missing,
        "canonical_rows": canonical_rows,
        "aliases_list": aliases,
        "repoints": repoints,
    }


def _dump(result: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "canonical_rows.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "id_canonico", "existing_ensembles_id", "kind", "family", "name",
            "description", "voices",
        ])
        w.writeheader()
        w.writerows(result["canonical_rows"])
    with (OUT_DIR / "aliases.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["raw_code", "id_canonico", "raw_ensembles_id"])
        w.writeheader()
        w.writerows(result["aliases_list"])
    with (OUT_DIR / "repoints.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["raw_ensembles_id", "to_id_canonico"])
        w.writeheader()
        w.writerows(result["repoints"])
    summary = {k: v for k, v in result.items() if not k.endswith(("_rows", "_list", "repoints"))}
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="solo planifica (por defecto)")
    parser.parse_args()
    result = plan()
    _dump(result)
    print(f"filas originales        : {result['original_rows']}")
    print(f"ids canonicos           : {result['canonical_ids']}")
    print(f"filas canonicas nuevas  : {result['new_rows']}")
    print(f"aliases                 : {result['aliases']}")
    print(f"grupos con alias        : {result['groups_with_alias']}")
    print(f"originales sin cubrir   : {len(result['missing_original'])}")
    print(f"aliases mal dirigidos   : {len(result['bad_alias'])}")
    print(f"VOICES sin voces        : {len(result['voice_missing'])}")
    print(f"plan escrito en {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
