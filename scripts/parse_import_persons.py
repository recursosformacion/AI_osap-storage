"""Re-parse de `works_person_import` a personas+roles y atribuciones (staging, sin aplicar).

Docstring/resumen (regla del repo): convierte el texto libre del import (PDMX/CPDL) en filas
tipadas —persona+rol o atribución— y las deja en `import_person_parse` para revisión; nunca
escribe en `works_person_roles` ni crea personas.

Uso:
    python -m scripts.parse_import_persons                # dry-run (por defecto): solo métricas
    python -m scripts.parse_import_persons --apply        # refresca import_person_parse
                                                         # (tabla derivada: se vacía y se reescribe)
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

from application.services.import_person_parser import (
    canonical_name_key,
    looks_contaminated,
    parse_import_name,
    role_id_for,
)
from domain.services.composer_names import normalize_composer_name
from infrastructure.config import Settings
from infrastructure.db.connection import Database

_IGNORED_IMPORT_ROLES = {"artist"}


async def _load_catalogue(db: Database) -> tuple[dict[str, str | None], dict[str, str], dict[str, str]]:
    """Catálogo para resolver: (nombre normalizado -> id | None, id -> clave lógica, id -> nombre).

    Solo se aceptan personas **existentes, activas y no fusionadas**: los alias pueden apuntar a
    personas retiradas tras una fusión (`persons_merged_into`) y eso rompería la FK del staging.

    La clave lógica (`person_key`) es un ancla tipada (`viaf:…`, `musicbrainz:…`) o, en su
    defecto, `name:<normalizado>`: estable entre entornos, a diferencia del UUID.
    """
    mapping: dict[str, str | None] = {}
    anchor_key: dict[str, str] = {}
    name_by_id: dict[str, str] = {}
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT persons_id, persons_name FROM persons "
            "WHERE persons_merged_into IS NULL AND persons_status = 'active'"
        )
        for row in await cur.fetchall():
            person_id = str(row["persons_id"])
            name_by_id[person_id] = str(row["persons_name"])
            key = normalize_composer_name(str(row["persons_name"]))
            if key:
                mapping[key] = person_id if key not in mapping else None
        await cur.execute(
            "SELECT a.person_id, a.person_aliases_normalized_alias FROM persons_aliases a "
            "JOIN persons p ON p.persons_id = a.person_id "
            "WHERE p.persons_merged_into IS NULL AND p.persons_status = 'active'"
        )
        for row in await cur.fetchall():
            key = str(row["person_aliases_normalized_alias"] or "")
            if key and key not in mapping:
                mapping[key] = str(row["person_id"])
        await cur.execute(
            "SELECT persons_id, identity_type, identity_value, identity_name_norm FROM persons_identity "
            "WHERE identity_is_anchor = 1"
        )
        for row in await cur.fetchall():
            person_id = str(row["persons_id"])
            tipo = str(row["identity_type"] or "").strip().lower()
            valor = str(row["identity_value"] or "").strip()
            if tipo in ("viaf", "musicbrainz", "mbid", "isni") and valor:
                anchor_key[person_id] = f"{tipo}:{valor}"
            elif person_id not in anchor_key:
                norm = str(row["identity_name_norm"] or "").strip()
                if norm:
                    anchor_key[person_id] = f"name:{norm}"
    return mapping, anchor_key, name_by_id


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="vuelca a import_person_parse")
    parser.add_argument("--limit", type=int, default=0, help="procesar solo N filas (prueba)")
    parser.add_argument("--json", type=Path, default=None, help="escribir informe JSON")
    args = parser.parse_args()

    settings = Settings()  # type: ignore[call-arg]
    db = Database(settings)
    catalogue, anchor_key, name_by_id = await _load_catalogue(db)

    sql = (
        "SELECT id, works_id, works_person_import_name AS name, "
        "works_person_import_role AS role, works_person_import_source AS source "
        "FROM works_person_import"
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
    sanitized = 0
    target_contaminated = 0
    needs_review = 0
    roles_sin_rol: set[str] = set()
    nombres_nuevos: dict[str, int] = defaultdict(int)
    obras_persona: set[int] = set()
    obras_atribucion: set[int] = set()
    pendientes: list[dict] = []

    for row in rows:
        if str(row["role"]) in _IGNORED_IMPORT_ROLES:
            kinds["ignored_artist"] += 1
            continue
        parsed = parse_import_name(row["name"], str(row["role"]))
        kinds[parsed.kind] += 1
        por_origen[f"{row['source']}:{parsed.kind}"] += 1
        if parsed.attribution_status:
            # Atribución no personal, sola o acompañada de personas ("traditional carol arr. X").
            attribution_status[str(parsed.attribution_status)] += 1
            obras_atribucion.add(int(row["works_id"]))
            pendientes.append({
                "kind": "attribution", "works_id": int(row["works_id"]), "import_row_id": int(row["id"]),
                "person_name_raw": None, "person_name_norm": None, "role_key": "", "role_id": None,
                "attribution_status": parsed.attribution_status, "person_id": None,
                "source": row["source"], "evidence": parsed.reason, "status": "pending",
            })
        if parsed.kind == "attribution":
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
            clean = person.name
            norm = canonical_name_key(normalize_composer_name(clean))[:191]
            if not norm:
                continue
            flags = list(person.flags)
            if flags:
                sanitized += 1
            roles[person.role_key] += 1
            obras_persona.add(int(row["works_id"]))
            role_id = role_id_for(person.role_key)
            person_id: str | None = None
            if norm in catalogue:
                candidate = catalogue[norm]
                if candidate is None:
                    status = "ambiguous"
                    ambiguous += 1
                elif looks_contaminated(name_by_id.get(candidate, "")):
                    # La FK casaría, pero la ficha del catálogo está sucia: no es una resolución
                    # fiable. Se conserva como candidato para que lo decida la revisión.
                    person_id = candidate
                    status = "review_target_contaminated"
                    target_contaminated += 1
                else:
                    person_id = candidate
                    status = "resolved_sanitized" if flags else "resolved"
                    resolved += 1
            elif "truncated_prefix" in flags:
                status = "needs_review"
                needs_review += 1
            else:
                status = "new_person"
                new_person += 1
                nombres_nuevos[norm] += 1
            if role_id is None:
                # El rol del texto no existe en el catálogo (p. ej. 'adapter'): cola de decisión.
                status = "role_missing"
                roles_sin_rol.add(person.role_key)
            person_key = canonical_name_key(anchor_key.get(person_id) if person_id else None) or f"name:{norm}"
            pendientes.append({
                "kind": "person", "works_id": int(row["works_id"]), "import_row_id": int(row["id"]),
                "person_name_raw": str(row["name"])[:512], "person_name_clean": clean[:512],
                "person_name_norm": norm,
                "sanitize_flags": json.dumps(flags, ensure_ascii=False)[:255] if flags else None,
                "person_key": person_key,
                "role_key": person.role_key, "role_id": role_id,
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
        "personas_con_saneamiento": sanitized,
        "resoluciones_a_ficha_contaminada": target_contaminated,
        "necesitan_revision_por_truncamiento": needs_review,
        "roles_sin_rol_en_catalogo": sorted(roles_sin_rol),
        "nombres_nuevos_unicos": len(nombres_nuevos),
        "filas_staging": len(pendientes),
        "top_nombres_nuevos": sorted(nombres_nuevos.items(), key=lambda item: -item[1])[:15],
        "aplicado": False,
    }

    if args.apply:
        insert_sql = (
            "INSERT INTO import_person_parse "
            "(works_id, import_row_id, kind, person_name_raw, person_name_clean, person_name_norm, "
            " sanitize_flags, person_key, role_key, role_id, attribution_status, person_id, source, "
            " evidence_json, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE kind=VALUES(kind), person_name_clean=VALUES(person_name_clean), "
            "sanitize_flags=VALUES(sanitize_flags), person_key=VALUES(person_key), "
            "role_id=VALUES(role_id), attribution_status=VALUES(attribution_status), "
            "person_id=VALUES(person_id), evidence_json=VALUES(evidence_json), status=VALUES(status)"
        )
        params = [
            (
                item["works_id"], item["import_row_id"], item["kind"], item["person_name_raw"],
                item.get("person_name_clean"), item["person_name_norm"] or "",
                item.get("sanitize_flags"), item.get("person_key"),
                item["role_key"], item["role_id"], item["attribution_status"], item["person_id"],
                item["source"],
                json.dumps([{"type": "import_parse", "text": item["evidence"]}], ensure_ascii=False),
                item["status"],
            )
            for item in pendientes
        ]
        async with db.transaction() as conn, conn.cursor() as cur:
            # Tabla derivada: se refresca entera para que no queden filas de esquemas/nombres
            # anteriores (el índice único cambia al cambiar `person_name_norm`).
            await cur.execute("DELETE FROM import_person_parse")
            for start in range(0, len(params), 1000):
                await cur.executemany(insert_sql, params[start: start + 1000])
        informe["aplicado"] = True

    if args.json:
        args.json.write_text(json.dumps(informe, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(informe, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
