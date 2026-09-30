"""Re-parse de `works_person_import` a personas+roles y atribuciones (staging, sin aplicar).

Docstring/resumen (regla del repo): convierte el texto libre del import (PDMX/CPDL) en filas
tipadas —persona+rol o atribución— y las deja en `import_person_parse` para revisión; nunca
escribe en `works_person_roles` ni crea personas.

Uso:
    python -m scripts.parse_import_persons                # dry-run (por defecto): solo métricas
    python -m scripts.parse_import_persons --apply        # vuelca a import_person_parse (idempotente)
    python -m scripts.parse_import_persons --limit 5000   # muestra
    python -m scripts.parse_import_persons --json out.json

Decisiones aplicadas (aprobadas): se ignoran las filas de rol `artist`; las atribuciones no
personales se proponen como `anonymous`/`traditional` (no como persona); el resultado va a una
tabla de staging separada.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from application.services.import_person_parser import parse_import_name, role_id_for
from domain.services.composer_names import normalize_composer_name
from infrastructure.config import Settings
from infrastructure.db.connection import Database

_IGNORED_IMPORT_ROLES = {"artist"}


async def _load_catalogue(db: Database) -> dict[str, str | None]:
    """Mapa nombre normalizado -> persons_id (None si hay más de una coincidencia)."""
    mapping: dict[str, str | None] = {}
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT persons_id, persons_name FROM persons")
        for row in await cur.fetchall():
            key = normalize_composer_name(str(row["persons_name"]))
            if key:
                mapping[key] = str(row["persons_id"]) if key not in mapping else None
        await cur.execute("SELECT person_id, person_aliases_normalized_alias FROM persons_aliases")
        for row in await cur.fetchall():
            key = str(row["person_aliases_normalized_alias"] or "")
            if key and key not in mapping:
                mapping[key] = str(row["person_id"])
    return mapping


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="vuelca a import_person_parse")
    parser.add_argument("--limit", type=int, default=0, help="procesar solo N filas (prueba)")
    parser.add_argument("--json", type=Path, default=None, help="escribir informe JSON")
    args = parser.parse_args()

    settings = Settings()  # type: ignore[call-arg]
    db = Database(settings)
    catalogue = await _load_catalogue(db)

    sql = (
        "SELECT id, works_id, works_person_import_name AS name, "
        "works_person_import_role AS role, works_person_import_source AS source "
        "FROM works_person_import WHERE works_person_import_role NOT IN ('artist')"
        + (f" LIMIT {int(args.limit)}" if args.limit else "")
    )
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        rows = [dict(r) for r in await cur.fetchall()]

    kinds: Counter = Counter()
    attribution_status: Counter = Counter()
    roles: Counter = Counter()
    por_origen: Counter = Counter()
    resolved = 0
    new_person = 0
    ambiguous = 0
    nombres_nuevos: dict[str, int] = defaultdict(int)
    obras_persona: set[int] = set()
    obras_atribucion: set[int] = set()
    pendientes: list[dict] = []

    for row in rows:
        parsed = parse_import_name(row["name"], str(row["role"]))
        kinds[parsed.kind] += 1
        por_origen[f"{row['source']}:{parsed.kind}"] += 1
        if parsed.kind == "attribution":
            attribution_status[str(parsed.attribution_status)] += 1
            obras_atribucion.add(int(row["works_id"]))
            pendientes.append({
                "kind": "attribution", "works_id": int(row["works_id"]), "import_row_id": int(row["id"]),
                "person_name_raw": None, "person_name_norm": None, "role_key": "", "role_id": None,
                "attribution_status": parsed.attribution_status, "person_id": None,
                "source": row["source"], "evidence": parsed.reason, "status": "pending",
            })
            continue
        if parsed.kind == "junk":
            pendientes.append({
                "kind": "junk", "works_id": int(row["works_id"]), "import_row_id": int(row["id"]),
                "person_name_raw": str(row["name"])[:512],
                "person_name_norm": normalize_composer_name(str(row["name"]))[:191],
                "role_key": "", "role_id": None, "attribution_status": None, "person_id": None,
                "source": row["source"], "evidence": parsed.reason, "status": "pending",
            })
            continue
        for person in parsed.persons:
            norm = normalize_composer_name(person.name)[:191]
            if not norm:
                continue
            roles[person.role_key] += 1
            obras_persona.add(int(row["works_id"]))
            if norm in catalogue:
                person_id = catalogue[norm]
                status = "resolved" if person_id else "new_person"
                if person_id:
                    resolved += 1
                else:
                    ambiguous += 1
            else:
                person_id = None
                status = "new_person"
                new_person += 1
                nombres_nuevos[norm] += 1
            pendientes.append({
                "kind": "person", "works_id": int(row["works_id"]), "import_row_id": int(row["id"]),
                "person_name_raw": person.name[:512], "person_name_norm": norm,
                "role_key": person.role_key, "role_id": role_id_for(person.role_key),
                "attribution_status": None, "person_id": person_id, "source": row["source"],
                "evidence": person.evidence, "status": status,
            })

    informe = {
        "filas_leidas": len(rows),
        "por_kind": dict(kinds),
        "atribuciones_por_tipo": dict(attribution_status),
        "personas_por_rol": dict(roles.most_common()),
        "por_origen_kind": dict(por_origen.most_common()),
        "obras_con_persona_propuesta": len(obras_persona),
        "obras_con_atribucion_propuesta": len(obras_atribucion),
        "personas_resueltas_en_catalogo": resolved,
        "personas_nuevas": new_person,
        "nombres_ambiguos": ambiguous,
        "nombres_nuevos_unicos": len(nombres_nuevos),
        "filas_staging": len(pendientes),
        "top_nombres_nuevos": sorted(nombres_nuevos.items(), key=lambda item: -item[1])[:15],
        "aplicado": False,
    }

    if args.apply:
        async with db.transaction() as conn, conn.cursor() as cur:
            for item in pendientes:
                await cur.execute(
                    "INSERT INTO import_person_parse "
                    "(works_id, import_row_id, kind, person_name_raw, person_name_norm, role_key, role_id, "
                    " attribution_status, person_id, source, evidence_json, status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE kind=VALUES(kind), role_id=VALUES(role_id), "
                    "attribution_status=VALUES(attribution_status), person_id=VALUES(person_id), "
                    "evidence_json=VALUES(evidence_json)",
                    (
                        item["works_id"], item["import_row_id"], item["kind"], item["person_name_raw"],
                        item["person_name_norm"] or "", item["role_key"], item["role_id"],
                        item["attribution_status"], item["person_id"], item["source"],
                        json.dumps([{"type": "import_parse", "text": item["evidence"]}], ensure_ascii=False),
                        item["status"],
                    ),
                )
        informe["aplicado"] = True

    if args.json:
        args.json.write_text(json.dumps(informe, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(informe, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
