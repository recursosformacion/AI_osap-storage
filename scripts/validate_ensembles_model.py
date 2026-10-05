#!/usr/bin/env python
"""Validación final (Bloque 4) del modelo canónico de ensembles — SOLO LECTURA.

Comprueba, sin escribir nada:
  1. Canonicalización: `canonical_ensemble(code) == code` en todas las filas.
  2. Integridad: `representations.ensemble_code` y aliases existen; `work_ensembles` sin huérfanos.
  3. Reconstrucción: `ensemble_voices` reproduce la firma agregada de cada formación VOICES.
  4. Firmas: `voice_signature` recalculada desde `ensembles -> ensemble_voices` sin discrepancias.
  5. Aliases: cada `raw_code` resuelve a su canónico.
  6. Expresiones originales: canónicos + aliases cubren la población anterior (CSV).
  7. Recursos: solo conteo/huérfanos de `works_resources` (Bloque 3 no crea recursos).

Uso (osap-storage, venv, `PYTHONPATH=.`):
    python scripts/validate_ensembles_model.py --previous-codes <ruta/ensembles.csv>
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import defaultdict
from pathlib import Path

from domain.services.ensemble_canonical import VOICE_ORDER, canonical_ensemble
from infrastructure.config import Settings
from infrastructure.db.connection import Database

NAME_SYMBOL = {
    "Soprano": "S", "Mezzo-soprano": "MZ", "Contralto": "A", "Countertenor": "CT",
    "Tenor": "T", "Baritone": "BAR", "Bass": "B",
}


def _letters(counts: dict[str, int]) -> str:
    return "".join(sym * counts[sym] for sym in VOICE_ORDER if counts.get(sym, 0) > 0)


def _frequency(counts: dict[str, int]) -> str:
    return "".join(f"{sym}{counts[sym]}" for sym in VOICE_ORDER if counts.get(sym, 0) > 0)


async def _load() -> dict:
    db = Database(Settings())  # type: ignore[call-arg]
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id, voices_name FROM voices")
        voice_sym = {int(r["id"]): NAME_SYMBOL.get(str(r["voices_name"])) for r in await cur.fetchall()}
        await cur.execute("SELECT id, ensembles_code FROM ensembles")
        ensembles = {int(r["id"]): str(r["ensembles_code"] or "") for r in await cur.fetchall()}
        await cur.execute("SELECT ensembles_id, voices_id, ensemble_voices_quantity FROM ensemble_voices")
        ev_rows = [dict(r) for r in await cur.fetchall()]
        await cur.execute("SELECT raw_code, ensembles_id FROM ensembles_aliases")
        aliases = [dict(r) for r in await cur.fetchall()]
        await cur.execute("SELECT ensembles_id FROM work_ensembles")
        we_ids = [int(r["ensembles_id"]) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT id, representations_ensemble_code, representations_voice_signature "
            "FROM representations"
        )
        reps = [dict(r) for r in await cur.fetchall()]
        await cur.execute("SELECT COUNT(*) n FROM works_resources")
        resources = int((await cur.fetchone())["n"])
        await cur.execute(
            "SELECT COUNT(*) n FROM works_resources res LEFT JOIN representations r "
            "ON r.id = res.works_resources_representation_id WHERE r.id IS NULL"
        )
        res_orphans = int((await cur.fetchone())["n"])
    await db.close()
    return {"voice_sym": voice_sym, "ensembles": ensembles, "ev": ev_rows,
            "aliases": aliases, "we_ids": we_ids, "reps": reps,
            "resources": resources, "res_orphans": res_orphans}


def _previous_codes(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    with p.open(encoding="utf-8", newline="") as fh:
        return {str(row.get("ensembles_code", "") or "") for row in csv.DictReader(fh)}


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-codes", default=None)
    args = parser.parse_args()

    data = asyncio.run(_load())
    ensembles: dict[int, str] = data["ensembles"]
    codes = set(ensembles.values())
    voice_sym = data["voice_sym"]

    # 1. Canonicalización
    no_idem = sorted(c for c in codes if canonical_ensemble(c).id_canonico != c)

    # 3. Reconstrucción desde ensemble_voices
    ev_by_ens: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in data["ev"]:
        sym = voice_sym.get(int(row["voices_id"]))
        if sym:
            ev_by_ens[int(row["ensembles_id"])][sym] += int(row["ensemble_voices_quantity"])
    voces_incon: list[tuple[str, str, str]] = []
    reconstruccion_exacta = reconstruccion_agregada = 0
    for ens_id, code in ensembles.items():
        info = canonical_ensemble(code)
        if info.kind != "VOICES":
            continue
        rebuilt = _letters(ev_by_ens.get(ens_id, {}))
        aggregate = _letters(dict(info.voice_counts))
        if rebuilt != aggregate:
            voces_incon.append((code, rebuilt, aggregate))
        elif code == aggregate:
            reconstruccion_exacta += 1
        else:
            reconstruccion_agregada += 1

    # 2. Integridad de referencias
    rep_code_huerfanos = sum(
        1 for r in data["reps"]
        if r["representations_ensemble_code"] not in (None, "") and r["representations_ensemble_code"] not in codes
    )
    alias_huerfanos = sum(1 for a in data["aliases"] if int(a["ensembles_id"]) not in ensembles)
    we_huerfanos = sum(1 for eid in data["we_ids"] if eid not in ensembles)

    # 4. Firmas
    freq_by_ens = {eid: _frequency(counts) for eid, counts in ev_by_ens.items()}
    code_to_eid = {c: eid for eid, c in ensembles.items()}
    expected_sig = {c: (freq_by_ens.get(eid) or None) for c, eid in code_to_eid.items()}
    firmas_incon = 0
    firma_null_con_voces = 0
    firma_no_null_sin_voces = 0
    for r in data["reps"]:
        code = r["representations_ensemble_code"]
        stored = r["representations_voice_signature"]
        if code in (None, ""):
            if stored not in (None, ""):
                firma_no_null_sin_voces += 1
            continue
        expected = expected_sig.get(code)
        if expected != (stored or None):
            firmas_incon += 1
        if expected and stored in (None, ""):
            firma_null_con_voces += 1

    # 5. Aliases resuelven
    aliases_mal = sum(
        1 for a in data["aliases"]
        if int(a["ensembles_id"]) in ensembles
        and canonical_ensemble(str(a["raw_code"] or "")).id_canonico != ensembles[int(a["ensembles_id"])]
    )
    canon_con_alias = len({int(a["ensembles_id"]) for a in data["aliases"]})

    # 6. Expresiones originales
    previous = _previous_codes(args.previous_codes)
    covered = codes | {str(a["raw_code"] or "") for a in data["aliases"]}
    perdidas = sorted(previous - covered) if previous else []
    prev_groups: dict[str, int] = defaultdict(int)
    for c in previous:
        prev_groups[canonical_ensemble(c).id_canonico] += 1
    colapsados = sum(1 for n in prev_groups.values() if n > 1)

    print("=" * 60)
    print("INFORME FINAL — modelo canónico de ensembles (solo lectura)")
    print("=" * 60)
    print(f"filas canónicas ......................: {len(codes)}")
    print(f"aliases ..............................: {len(data['aliases'])}")
    print(f"canónicos con alias ..................: {canon_con_alias}")
    print(f"grupos colapsados (>1 código) ........: {colapsados}")
    print(f"población previa (códigos) ...........: {len(previous) if previous else 'n/d'}")
    print(f"work_ensembles huérfanos .............: {we_huerfanos}")
    print(f"alias huérfanos ......................: {alias_huerfanos}")
    print(f"representations_ensemble_code huérfanos: {rep_code_huerfanos}")
    print(f"ensemble_voices inconsistentes .......: {len(voces_incon)}")
    print(f"  reconstrucción exacta (code==voces) : {reconstruccion_exacta}")
    print(f"  reconstrucción agregada (| / solo)  : {reconstruccion_agregada}")
    print(f"voice_signature inconsistentes .......: {firmas_incon}")
    print(f"  firma NULL con voces ...............: {firma_null_con_voces}")
    print(f"  firma no-NULL sin voces ............: {firma_no_null_sin_voces}")
    print(f"códigos no idempotentes ..............: {len(no_idem)}")
    print(f"aliases que no resuelven a su canónico: {aliases_mal}")
    print(f"expresiones originales no cubiertas ..: {len(perdidas)}")
    print(f"(recursos works_resources: {data['resources']} | sin representación (preexistente, "
          f"FUERA DE ALCANCE): {data['res_orphans']} — Bloque 3 no toca works_resources)")
    for label, items in (("no idempotentes", no_idem[:8]),
                         ("voces inconsistentes", [v[0] for v in voces_incon[:8]]),
                         ("perdidas", perdidas[:8])):
        if items:
            print(f"  {label}: {items}")
    # Los recursos quedan fuera del gate del modelo de ensembles (preexistente, no de Bloque 3).
    ok = not (no_idem or voces_incon or rep_code_huerfanos or alias_huerfanos or we_huerfanos
              or firmas_incon or firma_null_con_voces or firma_no_null_sin_voces
              or aliases_mal or perdidas)
    print("=" * 60)
    print("RESULTADO:", "OK (0 discrepancias)" if ok else "REVISAR")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
