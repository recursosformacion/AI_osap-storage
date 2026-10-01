"""Repositorio del motor de revisión.

INVARIANTE: este repositorio **solo** escribe en `review_decisions`. No toca `works`,
`persons`, `works_person_roles` ni `work_attribution_audit`. La materialización es idempotente
(`INSERT IGNORE` por `decision_key`) y nunca altera una decisión humana existente.
"""

from __future__ import annotations

import json
from typing import Any

from infrastructure.db.connection import Database

_COLUMNAS = (
    "decision_key", "item_key", "decision_type", "person_key", "work_key", "role_key",
    "decision", "target_person_key", "attribution_status", "evidence_json", "notes",
    "decided_by", "batch",
)


class SqlReviewRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def unidades_tramo(self, tramo: str, role_key: str | None, limite: int) -> list[dict[str, Any]]:
        """Unidades de identidad de un tramo (A/B/…) para preparar un lote."""
        condiciones = ["item_type='identity_cluster'"]
        parametros: list[Any] = []
        if tramo.upper() == "A":
            condiciones.append("estados='resolved'")
            # Los patrones van como parámetros: un `%` literal en el SQL rompe el formateo.
            condiciones.append(
                "(person_key LIKE %s OR person_key LIKE %s OR person_key LIKE %s OR person_key LIKE %s)"
            )
            parametros.extend(["viaf:%", "musicbrainz:%", "mbid:%", "isni:%"])
        elif tramo.upper() == "B":
            condiciones.append("estados='resolved'")
            condiciones.append("person_key LIKE %s")
            parametros.append("name:%")
        else:
            condiciones.append("estados LIKE %s")
            parametros.append(f"%{tramo.lower()}%")
        if role_key:
            condiciones.append("FIND_IN_SET(%s, roles) > 0")
            parametros.append(role_key)
        sql = (
            f"SELECT item_key, person_key, role_key, attribution_status, filas, obras, roles, estados, "
            f"candidatos_json, contexto_json FROM review_items WHERE {' AND '.join(condiciones)} "
            f"ORDER BY obras DESC, item_key LIMIT %s"
        )
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, [*parametros, limite])
            return [dict(r) for r in await cur.fetchall()]

    async def conflictos(self) -> list[dict[str, Any]]:
        """Obras con propuesta de persona y de atribución a la vez (plan incompleto)."""
        sql = (
            "SELECT work_key, attribution_status, contexto_json FROM review_items "
            "WHERE item_type='work_attribution' "
            "AND JSON_EXTRACT(contexto_json,'$.conflicto_persona_atribucion') = TRUE "
            "ORDER BY work_key"
        )
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql)
            filas = [dict(r) for r in await cur.fetchall()]
            conflictos: list[dict[str, Any]] = []
            for fila in filas:
                contexto = json.loads(fila["contexto_json"] or "{}")
                claves = [
                    str(clave) for clave in (contexto.get("clusters_identidad_relacionados") or [])
                    if str(clave).startswith("identity_cluster")
                ]
                personas: list[dict[str, Any]] = []
                if claves:
                    marcadores = ",".join(["%s"] * len(claves))
                    await cur.execute(
                        f"SELECT person_key, role_key, obras, candidatos_json FROM review_items "
                        f"WHERE item_type='identity_cluster' AND item_key IN ({marcadores})",
                        claves,
                    )
                    personas = [dict(r) for r in await cur.fetchall()]
                conflictos.append({
                    "item_key": f"conflict|{fila['work_key']}|",
                    "work_key": fila["work_key"],
                    "person_key": (personas[0]["person_key"] if personas else None),
                    "role_key": (personas[0]["role_key"] if personas else None),
                    "attribution_status": fila["attribution_status"],
                    "obras": 1,
                    "personas": personas,
                    "contexto": contexto,
                })
            return conflictos

    async def decisiones_existentes(self, decision_keys: list[str]) -> dict[str, str]:
        if not decision_keys:
            return {}
        marcadores = ",".join(["%s"] * len(decision_keys))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT decision_key, decision FROM review_decisions WHERE decision_key IN ({marcadores})",
                decision_keys,
            )
            return {str(r["decision_key"]): str(r["decision"]) for r in await cur.fetchall()}

    async def insertar_decisiones(self, filas: list[dict[str, Any]]) -> int:
        """INSERT IGNORE: repetir un lote no duplica ni altera decisiones existentes."""
        if not filas:
            return 0
        sql = (
            "INSERT IGNORE INTO review_decisions (" + ",".join(f"`{c}`" for c in _COLUMNAS) + ") "
            "VALUES (" + ",".join(["%s"] * len(_COLUMNAS)) + ")"
        )
        parametros = [tuple(fila.get(c) for c in _COLUMNAS) for fila in filas]
        insertadas = 0
        async with self._db.transaction() as conn, conn.cursor() as cur:
            for inicio in range(0, len(parametros), 500):
                await cur.executemany(sql, parametros[inicio: inicio + 500])
                insertadas += int(cur.rowcount or 0)
        return insertadas
