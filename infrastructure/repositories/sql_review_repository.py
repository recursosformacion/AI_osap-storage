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

_TRAMOS = ("A", "B", "C", "D", "E", "F")
_ANCLA_TIPADA = (
    "(person_key LIKE %s OR person_key LIKE %s OR person_key LIKE %s OR person_key LIKE %s)"
)


def condiciones_tramo(tramo: str) -> tuple[list[str], list[str]]:
    """Condiciones SQL y parámetros de un tramo de identidad, **disjuntos** por prioridad.

    Prioridad D > C > E > F > A > B (la misma del inventario): cada clúster cae en un único
    tramo. `estados` es una lista separada por comas (`resolved`, `ambiguous`, `new_person`,
    `resolved_sanitized`, `review_target_contaminated`). Los patrones van como **parámetros**
    porque un `%` literal en el SQL rompe el formateo con `%s`.
    """
    t = tramo.upper()
    if t not in _TRAMOS:
        raise ValueError(f"tramo de identidad inválido: {tramo} (esperado uno de {_TRAMOS})")
    p = {
        "contaminated": "%contaminated%", "sanitized": "%sanitized%",
        "new_person": "%new_person%", "ambiguous": "%ambiguous%", "resolved": "%resolved%",
    }
    no_cont, no_san, no_new, no_amb = (
        "estados NOT LIKE %s", "estados NOT LIKE %s", "estados NOT LIKE %s", "estados NOT LIKE %s",
    )
    if t == "D":
        return ["estados LIKE %s"], [p["contaminated"]]
    if t == "C":
        return [no_cont, "estados LIKE %s"], [p["contaminated"], p["sanitized"]]
    if t == "E":
        return (
            [no_cont, no_san, "estados LIKE %s"],
            [p["contaminated"], p["sanitized"], p["new_person"]],
        )
    if t == "F":
        return (
            [no_cont, no_san, no_new, "estados LIKE %s"],
            [p["contaminated"], p["sanitized"], p["new_person"], p["ambiguous"]],
        )
    # A / B: resueltos con o sin ancla tipada, excluyendo los estados con tratamiento propio.
    condiciones = [no_cont, no_san, no_new, no_amb, "estados LIKE %s"]
    parametros = [p["contaminated"], p["sanitized"], p["new_person"], p["ambiguous"], p["resolved"]]
    if t == "A":
        condiciones.append(_ANCLA_TIPADA)
        parametros.extend(["viaf:%", "musicbrainz:%", "mbid:%", "isni:%"])
    else:
        condiciones.append("person_key LIKE %s")
        parametros.append("name:%")
    return condiciones, parametros


class SqlReviewRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def unidades_tramo(self, tramo: str, role_key: str | None, limite: int) -> list[dict[str, Any]]:
        """Unidades de identidad de un tramo explícito (A–F) para preparar un lote."""
        extra, parametros = condiciones_tramo(tramo)
        condiciones = ["item_type='identity_cluster'", *extra]
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

    async def cluster_identidad(self, person_key: str, role_key: str | None = None) -> dict[str, Any] | None:
        """Clúster canónico de identidad por `person_key` (y `role_key` si se indica)."""
        condiciones = ["item_type='identity_cluster'", "person_key=%s"]
        parametros: list[Any] = [person_key]
        if role_key:
            condiciones.append("role_key=%s")
            parametros.append(role_key)
        sql = (
            f"SELECT item_key, person_key, role_key, filas, obras, roles, estados, candidatos_json, "
            f"contexto_json FROM review_items WHERE {' AND '.join(condiciones)} LIMIT 1"
        )
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, parametros)
            fila = await cur.fetchone()
            return dict(fila) if fila else None

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
                        f"SELECT person_key, role_key, roles, obras, candidatos_json FROM review_items "
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

    async def insertar_historial(self, filas: list[dict[str, Any]]) -> int:
        """Historial append-only: registra la decisión anterior y la nueva. Nunca se borra."""
        if not filas:
            return 0
        columnas = ("decision_key", "operation", "previous_decision", "new_decision", "reason",
                    "evidence_json", "decided_by")
        sql = (
            "INSERT INTO review_decision_history (" + ",".join(f"`{c}`" for c in columnas) + ") "
            "VALUES (" + ",".join(["%s"] * len(columnas)) + ")"
        )
        parametros = [tuple(fila.get(c) for c in columnas) for fila in filas]
        insertadas = 0
        async with self._db.transaction() as conn, conn.cursor() as cur:
            for inicio in range(0, len(parametros), 500):
                await cur.executemany(sql, parametros[inicio: inicio + 500])
                insertadas += int(cur.rowcount or 0)
        return insertadas

    async def actualizar_decision(self, decision_key: str, decision: str, notes: str | None) -> int:
        """Única vía de actualización de una decisión vigente: el mecanismo de corrección."""
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE review_decisions SET decision=%s, attribution_status="
                "CASE WHEN decision_type='attribution' THEN %s ELSE attribution_status END, notes=%s "
                "WHERE decision_key=%s",
                (decision, decision, notes, decision_key),
            )
            return int(cur.rowcount or 0)

    async def historial(self, decision_key: str) -> list[dict[str, Any]]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT operation, previous_decision, new_decision, reason, decided_by, decided_at "
                "FROM review_decision_history WHERE decision_key=%s ORDER BY id",
                (decision_key,),
            )
            return [dict(r) for r in await cur.fetchall()]

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
