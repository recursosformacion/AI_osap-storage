"""Construye la cola de revisión humana (`review_items`) desde el staging saneado (fase 015).

NO aplica nada al catálogo: solo materializa la **unidad de revisión** con claves lógicas.

Tres tipos de item:
  identity_cluster     un clúster por `person_key` (todas las filas que apuntan a la misma identidad
                       lógica, o al mismo nombre normalizado si no hay identidad resuelta)
  work_attribution     una obra con propuesta de atribución (`anonymous`/`traditional`)
  exception_ambiguous  una fila ambigua, con sus candidatos para poder elegir

Uso:
    python -m scripts.build_review_items             # dry-run: solo métricas
    python -m scripts.build_review_items --apply     # refresca review_items (tabla derivada)
    python -m scripts.build_review_items --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from application.services.import_person_parser import canonical_name_key
from domain.services.composer_names import normalize_composer_name
from infrastructure.config import Settings
from infrastructure.db.connection import Database

_ROLES_TRAMPA = ("review_target_contaminated", "resolved_sanitized", "ambiguous", "needs_review")


def build_work_key(origin: str | None, origin_id: str | None, works_key: str | None) -> str | None:
    """Clave lógica de obra, estable entre entornos (o None si no se puede construir)."""
    origen = canonical_name_key(origin).upper()
    identificador = canonical_name_key(origin_id)
    hash_pdmx = canonical_name_key(works_key)
    if origen == "CPDL" and identificador:
        return f"CPDL:{identificador}"
    if hash_pdmx:
        return f"PDMX:{hash_pdmx}"
    if identificador:
        return f"{origen or 'OTRO'}:{identificador}"
    return None


def build_item_key(
    item_type: str, work_key: str | None, person_key: str | None, role_key: str | None = None
) -> str:
    """Clave canónica del item (no nula), para idempotencia del refresco."""
    return "|".join(
        [item_type, canonical_name_key(work_key), canonical_name_key(person_key), canonical_name_key(role_key)]
    )


def build_decision_key(
    decision_type: str, work_key: str | None, person_key: str | None, role_key: str | None = None
) -> str:
    """Clave canónica de una decisión humana (misma forma que el item cuando aplica)."""
    return "|".join(
        [decision_type, canonical_name_key(work_key), canonical_name_key(person_key), canonical_name_key(role_key)]
    )


async def _candidates_by_name(db: Database) -> dict[str, list[dict[str, str]]]:
    """nombre normalizado -> [{id, name}] (personas + alias), para resolver ambigüedades."""
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT persons_id, persons_name FROM persons "
            "WHERE persons_status='active' AND persons_merged_into IS NULL"
        )
        for row in await cur.fetchall():
            key = normalize_composer_name(str(row["persons_name"]))
            if key:
                out[key].append({"id": str(row["persons_id"]), "name": str(row["persons_name"])})
        await cur.execute(
            "SELECT a.person_id, p.persons_name, a.person_aliases_normalized_alias FROM persons_aliases a "
            "JOIN persons p ON p.persons_id = a.person_id "
            "WHERE p.persons_status='active' AND p.persons_merged_into IS NULL"
        )
        for row in await cur.fetchall():
            key = str(row["person_aliases_normalized_alias"] or "")
            if not key:
                continue
            entry = {"id": str(row["person_id"]), "name": str(row["persons_name"])}
            if entry not in out[key]:
                out[key].append(entry)
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="refresca review_items (derivada)")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    settings = Settings()  # type: ignore[call-arg]
    db = Database(settings)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT s.id, s.kind, s.person_key, s.person_name_raw, s.person_name_clean, s.person_name_norm, "
            "s.role_key, s.attribution_status, s.person_id, s.status, s.sanitize_flags, s.works_id, "
            "w.works_title, w.works_origin, w.works_origin_id, w.works_key "
            "FROM import_person_parse s JOIN works w ON w.id = s.works_id"
        )
        rows = [dict(r) for r in await cur.fetchall()]
    candidatos = await _candidates_by_name(db)

    clusters: dict[str, dict[str, Any]] = {}
    atribuciones: dict[str, dict[str, Any]] = {}
    ambiguas: list[dict[str, Any]] = []
    sin_work_key = 0

    for row in rows:
        work_key = build_work_key(row["works_origin"], row["works_origin_id"], row["works_key"])
        if work_key is None:
            sin_work_key += 1
        if row["kind"] == "attribution":
            clave = work_key or f"work:{row['works_id']}"
            item = atribuciones.setdefault(clave, {
                "item_key": build_item_key("work_attribution", clave, None),
                "item_type": "work_attribution", "person_key": None, "work_key": work_key,
                "role_key": None, "attribution_status": row["attribution_status"],
                "filas": 0, "obras": 0, "_obras": set(), "_estados": set(), "_muestras": [],
            })
            item["filas"] += 1
            item["_obras"].add(row["works_id"])
            item["_estados"].add(row["attribution_status"])
            if len(item["_muestras"]) < 3:
                item["_muestras"].append({"titulo": row["works_title"], "origen": row["works_origin"]})
            continue

        if row["kind"] != "person":
            continue

        person_key = canonical_name_key(row["person_key"] or f"name:{row['person_name_norm']}")
        item = clusters.setdefault(person_key, {
            "item_key": build_item_key("identity_cluster", None, person_key),
            "item_type": "identity_cluster", "person_key": person_key, "work_key": None,
            "role_key": None, "attribution_status": None,
            "filas": 0, "obras": 0, "_obras": set(), "_roles": set(), "_estados": set(),
            "_candidatos": {}, "_muestras": [], "_excepcion": False,
        })
        item["filas"] += 1
        item["_obras"].add(row["works_id"])
        if row["role_key"]:
            item["_roles"].add(str(row["role_key"]))
        estado = str(row["status"] or "")
        item["_estados"].add(estado)
        if estado in _ROLES_TRAMPA or row["sanitize_flags"]:
            item["_excepcion"] = True
        if row["person_id"]:
            item["_candidatos"][str(row["person_id"])] = str(row["person_name_clean"] or "")
        if len(item["_muestras"]) < 3:
            item["_muestras"].append({
                "texto_origen": row["person_name_raw"], "nombre_limpio": row["person_name_clean"],
                "flags": row["sanitize_flags"], "obra": row["works_title"], "estado": estado,
            })

        if estado == "ambiguous":
            ambiguas.append({
                "item_key": build_item_key("exception_ambiguous", work_key, person_key, row["role_key"]),
                "item_type": "exception_ambiguous", "person_key": person_key, "work_key": work_key,
                "role_key": row["role_key"], "attribution_status": None,
                "filas": 1, "obras": 1,
                "roles": row["role_key"], "estados": estado,
                "candidatos_json": json.dumps(
                    candidatos.get(str(row["person_name_norm"] or ""), []), ensure_ascii=False
                ),
                "contexto_json": json.dumps({
                    "texto_origen": row["person_name_raw"], "nombre_limpio": row["person_name_clean"],
                    "obra": row["works_title"], "works_id_local": row["works_id"],
                }, ensure_ascii=False),
            })

    items: list[dict[str, Any]] = []
    for item in list(clusters.values()) + list(atribuciones.values()):
        items.append({
            "item_key": item["item_key"], "item_type": item["item_type"],
            "person_key": item["person_key"], "work_key": item["work_key"],
            "role_key": item["role_key"], "attribution_status": item["attribution_status"],
            "filas": item["filas"], "obras": len(item["_obras"]),
            "roles": ",".join(sorted(item.get("_roles", set())))[:255] or None,
            "estados": ",".join(sorted(item.get("_estados", set())))[:255] or None,
            "candidatos_json": json.dumps(item.get("_candidatos", {}), ensure_ascii=False) or None,
            "contexto_json": json.dumps(item.get("_muestras", []), ensure_ascii=False) or None,
        })
    items.extend(ambiguas)

    informe = {
        "filas_staging_leidas": len(rows),
        "items_total": len(items),
        "items_por_tipo": {
            tipo: sum(1 for i in items if i["item_type"] == tipo)
            for tipo in ("identity_cluster", "work_attribution", "exception_ambiguous")
        },
        "clusters_con_excepcion": sum(
            1 for item in clusters.values() if item["_excepcion"]
        ),
        "filas_sin_work_key": sin_work_key,
        "top_clusters_por_obras": sorted(
            ({"person_key": i["person_key"], "obras": i["obras"], "roles": i["roles"], "estados": i["estados"]}
             for i in items if i["item_type"] == "identity_cluster"),
            key=lambda x: -x["obras"],
        )[:10],
        "aplicado": False,
    }

    if args.apply:
        columnas = ("item_key", "item_type", "person_key", "work_key", "role_key", "attribution_status",
                    "filas", "obras", "roles", "estados", "candidatos_json", "contexto_json")
        sql = (
            "INSERT INTO review_items (" + ",".join(f"`{c}`" for c in columnas) + ") "
            "VALUES (" + ",".join(["%s"] * len(columnas)) + ")"
        )
        params = [tuple(item.get(c) for c in columnas) for item in items]
        async with db.transaction() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM review_items")
            for start in range(0, len(params), 500):
                await cur.executemany(sql, params[start: start + 500])
        informe["aplicado"] = True

    if args.json:
        args.json.write_text(json.dumps(informe, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(informe, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
