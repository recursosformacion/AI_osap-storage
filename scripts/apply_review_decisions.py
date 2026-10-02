"""Fase 6 — aplicador de `review_decisions` al catálogo. **Dry-run por defecto**.

Modos:
  plan   (por defecto): calcula el plan final y lo compara con el estado actual. No escribe.
  apply  --batch B --decided-by X: escribe `works_person_roles` + `work_attribution_audit`
         (una transacción por obra). Idempotente: no reaplica un lote vivo.
  revert --batch B: deshace **exactamente** lo que hizo ese `apply` (solo las filas que creó y
         que siguen igual; restaura el estado previo de las atribuciones). Marca `reverted_at`.

Decisiones:
  identity/accept          -> relaciones (obra×rol) del clúster contra la persona resuelta
  identity/map_to_existing -> relaciones del clúster contra la persona destino
  identity/not_a_person | leave_unresolved -> no aplica
  attribution/*            -> `works.works_attr_type` (ANONIMA/TRADICIONAL/DESCONOCIDO)
  conflict/atribucion_gana -> retira la relación de la persona en conflicto

Resolución `person_key -> persons_id`: anclas vía `persons_identity` (con fallback al `person_id`
que ya resolvió el parser); claves `name:` vía `import_person_parse`/índice de nombres (debe ser único).

    PYTHONPATH=. .venv/bin/python -m scripts.apply_review_decisions plan  --out plan_f6.json
    PYTHONPATH=. .venv/bin/python -m scripts.apply_review_decisions apply --batch F6-0001 --decided-by mgarcia
    PYTHONPATH=. .venv/bin/python -m scripts.apply_review_decisions revert --batch F6-0001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import aiomysql  # noqa: E402
from domain.services.composer_names import normalize_composer_name  # noqa: E402
from infrastructure.config import Settings  # noqa: E402

ANCLA_TIPO = {"viaf": "viaf", "musicbrainz": "musicbrainz", "mbid": "musicbrainz", "isni": "isni"}
ATTR_TYPE = {"anonymous": "ANONIMA", "traditional": "TRADICIONAL", "unknown": "DESCONOCIDO"}


def _clave_nombre(nombre: str | None) -> str:
    if not nombre:
        return ""
    return " ".join(sorted(normalize_composer_name(nombre).split()))


class Catalogo:
    def __init__(self) -> None:
        self.anclas: dict[str, set[str]] = defaultdict(set)
        self.ipp_person_id: dict[str, set[str]] = defaultdict(set)
        self.nombres: dict[str, set[str]] = defaultdict(set)
        self.relaciones_ipp: dict[str, list[dict]] = defaultdict(list)
        self.actual: set[tuple[int, str, int]] = set()


async def cargar(conn: aiomysql.Connection) -> Catalogo:
    c = Catalogo()
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT persons_id, identity_type, identity_value, identity_name_norm "
            "FROM persons_identity WHERE identity_value IS NOT NULL OR identity_name_norm IS NOT NULL"
        )
        for r in await cur.fetchall():
            if r["identity_value"]:
                c.anclas[f"{r['identity_type']}:{r['identity_value']}"].add(str(r["persons_id"]))
            if r["identity_name_norm"]:
                c.nombres[f"name:{r['identity_name_norm']}"].add(str(r["persons_id"]))
        await cur.execute("SELECT persons_id, persons_name FROM persons")
        for r in await cur.fetchall():
            clave = _clave_nombre(r["persons_name"])
            if clave:
                c.nombres[f"name:{clave}"].add(str(r["persons_id"]))
        await cur.execute("SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases")
        for r in await cur.fetchall():
            clave = _clave_nombre(r["a"])
            if clave:
                c.nombres[f"name:{clave}"].add(str(r["person_id"]))
        await cur.execute(
            "SELECT ipp.person_key, ipp.works_id, ipp.role_id, ipp.person_id "
            "FROM import_person_parse ipp WHERE ipp.kind='person' AND ipp.person_key IN "
            "(SELECT person_key FROM review_decisions WHERE decision_type='identity')"
        )
        works_ids: set[int] = set()
        for r in await cur.fetchall():
            pk = str(r["person_key"])
            c.relaciones_ipp[pk].append({"work_id": int(r["works_id"]), "role_id": r["role_id"]})
            works_ids.add(int(r["works_id"]))
            if r["person_id"]:
                c.ipp_person_id[pk].add(str(r["person_id"]))
        lista = list(works_ids)
        for i in range(0, len(lista), 5000):
            trozo = lista[i:i + 5000]
            marcadores = ",".join(["%s"] * len(trozo))
            await cur.execute(
                f"SELECT works_person_roles_work_id w, works_person_roles_person_id p, "
                f"works_person_roles_role_id r FROM works_person_roles "
                f"WHERE works_person_roles_work_id IN ({marcadores})",
                trozo,
            )
            for r in await cur.fetchall():
                c.actual.add((int(r["w"]), str(r["p"]), int(r["r"])))
    return c


def resolver(cat: Catalogo, person_key: str) -> tuple[str | None, str]:
    prefijo = person_key.split(":", 1)[0] if ":" in person_key else ""
    ipp = cat.ipp_person_id.get(person_key, set())
    if prefijo in ANCLA_TIPO:
        ids = cat.anclas.get(f"{ANCLA_TIPO[prefijo]}:{person_key.split(':', 1)[1]}", set())
        if len(ids) == 1:
            return next(iter(ids)), "ancla"
        if len(ipp) == 1:
            return next(iter(ipp)), "ancla_fallback_ipp"
        if len(ids) > 1 or len(ipp) > 1:
            return None, "ancla_ambigua"
        return None, "ancla_no_resuelta"
    ids = ipp or cat.nombres.get(person_key, set())
    if len(ids) == 1:
        return next(iter(ids)), "nombre"
    if not ids:
        return None, "name_sin_resolver"
    return None, "name_multiple"


async def _work_id(cur: aiomysql.cursors.Cursor, work_key: str) -> int | None:
    if work_key.startswith("PDMX:"):
        await cur.execute("SELECT id FROM works WHERE works_origin='PDMX' AND works_key=%s",
                          (work_key.split(":", 1)[1],))
    elif work_key.startswith("CPDL:"):
        await cur.execute("SELECT id FROM works WHERE works_origin='CPDL' AND works_origin_id=%s",
                          (work_key.split(":", 1)[1],))
    else:
        return None
    fila = await cur.fetchone()
    return int(fila["id"]) if fila else None


async def construir_plan(conn: aiomysql.Connection) -> dict[str, Any]:
    cat = await cargar(conn)
    adds: list[dict] = []
    removals: list[dict] = []
    attrs: list[dict] = []
    bloqueadas: list[dict] = []
    noop = 0
    por_decision: dict[str, dict[str, int]] = defaultdict(lambda: {"add": 0, "noop": 0, "bloqueadas": 0})
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT decision_type, decision, person_key, target_person_key, work_key, decision_key "
            "FROM review_decisions ORDER BY decision_type, decision_key"
        )
        decisiones = [dict(r) for r in await cur.fetchall()]
    for d in decisiones:
        tipo, dec = str(d["decision_type"]), str(d["decision"])
        if tipo == "identity":
            if dec in ("not_a_person", "leave_unresolved"):
                continue
            clave = str(d["person_key"])
            destino, via = resolver(cat, str(d["target_person_key"]) if dec == "map_to_existing" else clave)
            filas = cat.relaciones_ipp.get(clave, [])
            resumen = por_decision[dec]
            if destino is None:
                resumen["bloqueadas"] += 1
                bloqueadas.append({"person_key": clave, "decision": dec, "motivo": via, "relaciones": len(filas)})
                continue
            for f in filas:
                if not f["role_id"]:
                    continue
                terna = (f["work_id"], destino, int(f["role_id"]))
                if terna in cat.actual:
                    noop += 1
                    resumen["noop"] += 1
                else:
                    adds.append({"work_id": f["work_id"], "person_id": destino, "role_id": int(f["role_id"]),
                                 "decision_key": str(d["decision_key"])})
                    resumen["add"] += 1
        elif tipo == "attribution" and dec in ATTR_TYPE:
            async with conn.cursor() as cur2:
                wid = await _work_id(cur2, str(d["work_key"]))
            if wid:
                attrs.append({"work_id": wid, "attr_type": ATTR_TYPE[dec],
                              "decision_key": str(d["decision_key"])})
        elif tipo == "conflict" and dec == "atribucion_gana":
            persona, _ = resolver(cat, str(d["person_key"]))
            async with conn.cursor() as cur2:
                wid = await _work_id(cur2, str(d["work_key"]))
                if wid and persona:
                    await cur2.execute(
                        "SELECT works_person_roles_role_id r FROM works_person_roles "
                        "WHERE works_person_roles_work_id=%s AND works_person_roles_person_id=%s",
                        (wid, persona),
                    )
                    for r in await cur2.fetchall():
                        removals.append({"work_id": wid, "person_id": persona, "role_id": int(r["r"]),
                                         "decision_key": str(d["decision_key"])})
    return {"adds": adds, "removals": removals, "attrs": attrs, "blocked": bloqueadas,
            "noop": noop, "por_decision": {k: dict(v) for k, v in por_decision.items()}}


async def _audit(cur: aiomysql.cursors.Cursor, **campos: Any) -> None:
    columnas = ["work_id", "person_id", "role_id", "operation", "source", "evidence_json",
                "created_by", "review_decision_key", "batch", "before_json", "after_json"]
    valores = [campos.get(c) for c in columnas]
    await cur.execute(
        f"INSERT INTO work_attribution_audit ({', '.join(columnas)}) "
        f"VALUES ({', '.join(['%s'] * len(columnas))})",
        valores,
    )


async def aplicar(conn: aiomysql.Connection, plan: dict[str, Any], batch: str, decided_by: str) -> dict[str, Any]:
    async with conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) AS n FROM work_attribution_audit WHERE batch=%s AND reverted_at IS NULL",
                          (batch,))
        if int((await cur.fetchone())["n"]):
            raise RuntimeError(f"el lote {batch} ya está aplicado y vivo; revierte antes de reaplicar")
    por_obra: dict[int, dict[str, list[dict]]] = defaultdict(lambda: {"adds": [], "removals": [], "attrs": []})
    for a in plan["adds"]:
        por_obra[a["work_id"]]["adds"].append(a)
    for r in plan["removals"]:
        por_obra[r["work_id"]]["removals"].append(r)
    for t in plan["attrs"]:
        por_obra[t["work_id"]]["attrs"].append(t)

    insertadas = auditadas = restauradas = 0
    for work_id, ops in por_obra.items():
        await conn.begin()
        async with conn.cursor() as cur:
            for r in ops["removals"]:
                await cur.execute("DELETE FROM works_person_roles WHERE works_person_roles_work_id=%s "
                                  "AND works_person_roles_person_id=%s AND works_person_roles_role_id=%s",
                                  (work_id, r["person_id"], r["role_id"]))
                if cur.rowcount:
                    await _audit(cur, work_id=work_id, person_id=r["person_id"], role_id=r["role_id"],
                                 operation="remove", source="manual", created_by=decided_by,
                                 review_decision_key=r["decision_key"], batch=batch)
                    auditadas += 1
            for a in ops["adds"]:
                await cur.execute("INSERT IGNORE INTO works_person_roles "
                                  "(works_person_roles_work_id, works_person_roles_person_id, "
                                  "works_person_roles_role_id, works_person_roles_order) VALUES (%s,%s,%s,0)",
                                  (work_id, a["person_id"], a["role_id"]))
                if cur.rowcount:
                    insertadas += 1
                    await _audit(cur, work_id=work_id, person_id=a["person_id"], role_id=a["role_id"],
                                 operation="assign", source="manual", created_by=decided_by,
                                 review_decision_key=a["decision_key"], batch=batch)
                    auditadas += 1
            for t in ops["attrs"]:
                await cur.execute("SELECT works_attr_type a, works_attribution_note n FROM works WHERE id=%s",
                                  (work_id,))
                antes = await cur.fetchone()
                await cur.execute("UPDATE works SET works_attr_type=%s WHERE id=%s", (t["attr_type"], work_id))
                await _audit(cur, work_id=work_id, person_id=None, role_id=None, operation="set_attribution",
                             source="manual", created_by=decided_by, review_decision_key=t["decision_key"],
                             batch=batch,
                             before_json=json.dumps({"attr_type": antes["a"], "note": antes["n"]}),
                             after_json=json.dumps({"attr_type": t["attr_type"], "note": antes["n"]}))
                auditadas += 1
                restauradas += 1
        await conn.commit()
    return {"insertadas": insertadas, "auditadas": auditadas, "obras": len(por_obra),
            "attr_cambios": restauradas}


async def revertir(conn: aiomysql.Connection, batch: str) -> dict[str, Any]:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id, work_id, person_id, role_id, operation, before_json "
            "FROM work_attribution_audit WHERE batch=%s AND reverted_at IS NULL ORDER BY id DESC",
            (batch,),
        )
        filas = [dict(r) for r in await cur.fetchall()]
        if not filas:
            return {"revertidas": 0, "aviso": "sin operaciones vivas para ese lote"}
        borradas = reinsertadas = restauradas = 0
        await conn.begin()
        for f in filas:
            if f["operation"] == "assign":
                await cur.execute("DELETE FROM works_person_roles WHERE works_person_roles_work_id=%s "
                                  "AND works_person_roles_person_id=%s AND works_person_roles_role_id=%s",
                                  (f["work_id"], f["person_id"], f["role_id"]))
                borradas += cur.rowcount
            elif f["operation"] == "remove":
                await cur.execute("INSERT IGNORE INTO works_person_roles "
                                  "(works_person_roles_work_id, works_person_roles_person_id, "
                                  "works_person_roles_role_id, works_person_roles_order) VALUES (%s,%s,%s,0)",
                                  (f["work_id"], f["person_id"], f["role_id"]))
                reinsertadas += cur.rowcount
            elif f["operation"] == "set_attribution":
                antes = json.loads(f["before_json"] or "{}")
                await cur.execute("UPDATE works SET works_attr_type=%s, works_attribution_note=%s WHERE id=%s",
                                  (antes.get("attr_type"), antes.get("note"), f["work_id"]))
                restauradas += 1
            await cur.execute("UPDATE work_attribution_audit SET reverted_at=NOW(6) WHERE id=%s", (f["id"],))
        await conn.commit()
    return {"revertidas": len(filas), "relaciones_borradas": borradas,
            "relaciones_reinsertadas": reinsertadas, "atribuciones_restauradas": restauradas}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=("plan", "apply", "revert"), nargs="?", default="plan")
    ap.add_argument("--batch", default=None)
    ap.add_argument("--decided-by", default="mgarcia")
    ap.add_argument("--out", default="/home/ocw/plan_f6.json")
    args = ap.parse_args()

    settings = Settings()  # type: ignore[call-arg]
    conn = await aiomysql.connect(
        host=settings.db_host, port=settings.db_port, user=settings.db_user,
        password=settings.db_password, db=settings.db_name, charset="utf8mb4",
        autocommit=False, cursorclass=aiomysql.DictCursor,
    )
    try:
        if args.modo == "plan":
            plan = await construir_plan(conn)
            informe = {
                "add_total": len(plan["adds"]), "noop_total": plan["noop"],
                "bloqueadas_total": len(plan["blocked"]), "atribuciones": len(plan["attrs"]),
                "retiradas": len(plan["removals"]),
                "relaciones_por_decision": plan["por_decision"],
                "bloqueadas": plan["blocked"][:50],
                "muestra_add": plan["adds"][:20], "attrs": plan["attrs"], "removals": plan["removals"],
            }
            Path(args.out).write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps({k: informe[k] for k in
                              ("add_total", "noop_total", "bloqueadas_total", "atribuciones",
                               "retiradas", "relaciones_por_decision")}, ensure_ascii=False, indent=1))
        elif args.modo == "apply":
            if not args.batch:
                ap.error("--batch requerido")
            plan = await construir_plan(conn)
            print(json.dumps(await aplicar(conn, plan, args.batch, args.decided_by), ensure_ascii=False, indent=1))
        else:
            if not args.batch:
                ap.error("--batch requerido")
            print(json.dumps(await revertir(conn, args.batch), ensure_ascii=False, indent=1))
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
