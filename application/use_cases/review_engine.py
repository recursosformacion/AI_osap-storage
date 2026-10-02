"""Motor de revisión humana: batch -> preview -> validación -> review_decisions.

Solo materializa DECISIONES HUMANAS. Nunca ejecuta nada sobre el catálogo:
`works`, `persons`, `works_person_roles` y `work_attribution_audit` quedan fuera de su alcance.

Guardarraíles implementados aquí:
1. Un batch no puede materializar si su preview no ha sido validado (`confirm` = hash del preview).
2. La materialización es idempotente por `decision_key`; nunca altera una decisión existente con
   otro valor (se detecta y se informa).
3. Los conflictos no admiten lote: exigen decisión explícita por obra.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from infrastructure.repositories.sql_review_repository import SqlReviewRepository

_DECISIONES_IDENTITY = ("accept", "map_to_existing", "create_person", "not_a_person", "leave_unresolved")
_DECISIONES_CONFLICT = ("persona_gana", "atribucion_gana", "revisar_manual")


class PreviewNoValidado(RuntimeError):
    """El hash de confirmación no corresponde al preview presentado."""


class DecisionExistenteDistinta(RuntimeError):
    """Ya hay una decisión humana para esa clave con otro valor: no se altera."""


@dataclass
class Preview:
    batch: str
    modo: str
    unidad: str
    decision: str
    filas: list[dict[str, Any]] = field(default_factory=list)
    muestra: list[dict[str, Any]] = field(default_factory=list)
    excepciones: list[dict[str, Any]] = field(default_factory=list)
    resumen: dict[str, Any] = field(default_factory=dict)

    def contenido(self) -> dict[str, Any]:
        return {
            "batch": self.batch, "modo": self.modo, "unidad": self.unidad, "decision": self.decision,
            "items": [f["item_key"] for f in self.filas], "muestra": self.muestra,
            "excepciones": self.excepciones, "resumen": self.resumen,
        }

    def hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.contenido(), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]


def _detalle_identidad(unidad: dict[str, Any]) -> dict[str, Any]:
    """Enriquece una unidad de identidad con propuesta, candidatos, evidencia y excepciones.

    La `excepcion` (motivo o `None`) replica el criterio del inventario: colisión de clave,
    destino contaminado o identidad saneada. Ser ambiguo/nuevo no es excepción: es el motivo del tramo.
    """
    try:
        contexto = json.loads(unidad.get("contexto_json") or "{}")
    except json.JSONDecodeError:
        contexto = {}
    try:
        candidatos = json.loads(unidad.get("candidatos_json") or "[]")
    except json.JSONDecodeError:
        candidatos = []
    estados = str(unidad.get("estados") or "")
    colision = bool(contexto.get("colision_de_clave"))
    motivos = ["colision_de_clave"] if colision else []
    if "contaminated" in estados:
        motivos.append("contaminated")
    if "sanitized" in estados:
        motivos.append("sanitized")
    detalle = dict(unidad)
    detalle.update({
        "propuesta": unidad.get("person_key"),
        "candidatos": candidatos,
        "evidencia": contexto.get("evidencia_union"),
        "patrones_origen": contexto.get("patrones_origen"),
        "nombres_vistos": contexto.get("nombres_vistos", []),
        "colisiones": colision,
        "estado": estados,
        "obras_cubiertas": int(unidad.get("obras") or 0),
        "excepcion": ",".join(motivos) if motivos else None,
    })
    return detalle


class ReviewEngine:
    def __init__(self, repo: SqlReviewRepository) -> None:
        self._repo = repo

    async def preview_tramo(
        self, tramo: str, decision: str, *, batch: str, role_key: str | None = None,
        limite: int = 5000, tamano_muestra: int = 5,
    ) -> Preview:
        """Prepara un lote de identidad (A–F): selección + detalle + muestra + excepciones + resumen.

        Cada unidad añade `propuesta`, `candidatos`, `evidencia`, `patrones_origen`, `colisiones`,
        `estado`, `obras_cubiertas` y `excepcion`. Para F (revisión individual) `propuesta` es el
        `person_key` del clúster canónico.
        """
        if decision not in _DECISIONES_IDENTITY:
            raise ValueError(f"decisión de identidad inválida: {decision}")
        unidades = await self._repo.unidades_tramo(tramo, role_key, limite)
        if not unidades:
            raise LookupError(f"sin unidades para el tramo {tramo}")
        filas = [_detalle_identidad(u) for u in unidades]
        muestra = filas[:tamano_muestra]
        excepciones = [
            {"item_key": u["item_key"], "person_key": u["person_key"],
             "nombres": u["nombres_vistos"][:6], "obras": u["obras"], "motivo": u["excepcion"]}
            for u in filas if u["excepcion"]
        ]
        return Preview(
            batch=batch, modo=f"bulk:{tramo.upper()}", unidad="identity_cluster", decision=decision,
            filas=filas, muestra=muestra, excepciones=excepciones,
            resumen={
                "unidades": len(filas),
                "obras": sum(int(u["obras"]) for u in filas),
                "roles": sorted({str(u["roles"] or "") for u in filas}),
                "excepciones": len(excepciones),
                "criterio": {"tramo": tramo.upper(), "role": role_key, "limite": limite},
            },
        )

    async def preview_conflictos(self, *, batch: str = "CONFLICTOS") -> Preview:
        """Los conflictos persona↔atribución: sin lote de aceptación, decisión explícita por obra."""
        filas = await self._repo.conflictos()
        return Preview(
            batch=batch, modo="individual", unidad="conflict", decision="",
            filas=filas, muestra=filas[:5], excepciones=[],
            resumen={"obras": len(filas)},
        )

    async def decidir_identidad(
        self, person_key: str, decision: str, *, decided_by: str,
        target_person_key: str | None = None, role_key: str | None = None,
        note: str | None = None, evidence: str | None = None, apply: bool = False,
    ) -> dict[str, Any]:
        """Decisión individual sobre el **clúster canónico** de identidad (`person_key`).

        Vocabulario: `accept` | `map_to_existing` | `create_person` | `not_a_person` | `leave_unresolved`.
        `map_to_existing` exige `--target-person` (persona destino concreta); el resto no lo admite.
        Operar aquí (y no sobre `ambiguous_identity`, que es una vista derivada) evita decidir dos veces
        las mismas obras: el clúster cubre sus obras ambiguas y resueltas.
        """
        if decision not in _DECISIONES_IDENTITY:
            raise ValueError(f"decisión de identidad inválida: {decision}")
        if decision == "map_to_existing" and not target_person_key:
            raise ValueError("map_to_existing exige --target-person")
        if decision != "map_to_existing" and target_person_key:
            raise ValueError(f"{decision} no admite --target-person")
        fila = await self._repo.cluster_identidad(person_key, role_key)
        if fila is None:
            raise LookupError(f"clúster de identidad inexistente: {person_key}")
        role = fila.get("role_key") or ""
        clave = f"identity||{person_key}|{role}"
        existentes = await self._repo.decisiones_existentes([clave])
        if existentes and existentes[clave] != decision:
            raise DecisionExistenteDistinta(
                f"ya hay decisión {existentes[clave]!r} para {person_key}; no se altera"
            )
        candidatos = json.loads(fila.get("candidatos_json") or "[]")
        nuevas = [] if existentes else [{
            "decision_key": clave,
            "item_key": fila["item_key"],
            "decision_type": "identity",
            "person_key": person_key,
            "work_key": None,
            "role_key": fila.get("role_key"),
            "decision": decision,
            "target_person_key": target_person_key,
            "attribution_status": None,
            "evidence_json": json.dumps(
                {"decision_mode": "individual", "batch": "IDENTIDAD",
                 "propuesta": person_key,
                 "candidatos": [c.get("person_key") for c in candidatos],
                 "researcher_note": evidence or note},
                ensure_ascii=False,
            ),
            "notes": note,
            "decided_by": decided_by,
            "batch": "IDENTIDAD",
        }]
        insertadas = await self._repo.insertar_decisiones(nuevas) if apply else 0
        return {
            "person_key": person_key, "decision": decision, "target_person_key": target_person_key,
            "ya_existente": bool(existentes), "insertadas": insertadas, "aplicado": apply,
        }

    async def decidir_atribucion(
        self, work_key: str, valor: str, *, decided_by: str, note: str | None = None,
        evidence: str | None = None, apply: bool = False
    ) -> dict[str, Any]:
        """Decisión de atribución de una obra (`anonymous|traditional|unknown|identified`).

        Solo una decisión `attribution` puede desembocar (en el aplicador de Fase 6) en escribir
        `works.works_attr_type`; nunca una decisión `identity`.
        """
        if valor not in ("anonymous", "traditional", "unknown", "identified"):
            raise ValueError(f"atribución inválida: {valor}")
        clave = f"attribution|{work_key}||"
        existentes = await self._repo.decisiones_existentes([clave])
        if existentes and existentes[clave] != valor:
            raise DecisionExistenteDistinta(
                f"ya hay decisión {existentes[clave]!r} para la atribución de {work_key}; no se altera"
            )
        nuevas = [] if existentes else [{
            "decision_key": clave,
            "item_key": f"work_attribution|{work_key}|",
            "decision_type": "attribution",
            "person_key": None,
            "work_key": work_key,
            "role_key": None,
            "decision": valor,
            "target_person_key": None,
            "attribution_status": valor,
            "evidence_json": json.dumps(
                {"decision_mode": "individual", "batch": "CONFLICTOS",
                 "researcher_note": evidence or note},
                ensure_ascii=False,
            ),
            "notes": note,
            "decided_by": decided_by,
            "batch": "CONFLICTOS",
        }]
        insertadas = await self._repo.insertar_decisiones(nuevas) if apply else 0
        return {
            "work_key": work_key, "decision": valor,
            "ya_existente": bool(existentes), "insertadas": insertadas, "aplicado": apply,
        }

    async def corregir_decision(
        self, decision_key: str, nuevo_valor: str, *, decided_by: str, reason: str,
        evidence: str | None = None, notes: str | None = None, apply: bool = False
    ) -> dict[str, Any]:
        """Corrige una decisión **conservando el historial** (append-only).

        Nunca se borra la decisión anterior: se registra `previous -> new` con motivo, quién y
        cuándo, y se actualiza la fila vigente por esta única vía. Repetir la misma corrección no
        duplica historial ni cambia nada.
        """
        if not reason:
            raise ValueError("la corrección exige un motivo")
        existentes = await self._repo.decisiones_existentes([decision_key])
        anterior = existentes.get(decision_key)
        if anterior is None:
            raise LookupError(f"no hay decisión registrada para {decision_key}")
        if anterior == nuevo_valor:
            return {"decision_key": decision_key, "estado": "sin_cambios", "vigente": anterior,
                    "historial": 0, "actualizada": 0, "aplicado": apply}
        fila_historial = {
            "decision_key": decision_key, "operation": "correct",
            "previous_decision": anterior, "new_decision": nuevo_valor, "reason": reason,
            "evidence_json": json.dumps({"correction_evidence": evidence}, ensure_ascii=False),
            "decided_by": decided_by,
        }
        if not apply:
            return {"decision_key": decision_key, "estado": "dry_run", "anterior": anterior,
                    "nuevo": nuevo_valor, "historial": 0, "actualizada": 0, "aplicado": False}
        historial = await self._repo.insertar_historial([fila_historial])
        actualizada = await self._repo.actualizar_decision(decision_key, nuevo_valor, notes)
        if actualizada != 1:
            raise PreviewNoValidado(f"no se pudo actualizar la decisión vigente {decision_key}")
        return {"decision_key": decision_key, "estado": "corregida", "anterior": anterior,
                "nuevo": nuevo_valor, "historial": historial, "actualizada": actualizada, "aplicado": True}

    async def decidir_conflicto(
        self, work_key: str, decision: str, *, decided_by: str, note: str | None = None,
        evidence: str | None = None, apply: bool = False
    ) -> dict[str, Any]:
        """Decisión individual de un conflicto persona↔atribución (no admite lote).

        `revisar_manual` deja la obra **deliberadamente fuera** del plan aplicable hasta que exista
        una decisión posterior suficiente.
        """
        if decision not in _DECISIONES_CONFLICT:
            raise ValueError(f"decisión de conflicto inválida: {decision}")
        conflictos = await self._repo.conflictos()
        fila = next((c for c in conflictos if c["work_key"] == work_key), None)
        if fila is None:
            raise LookupError(f"obra sin conflicto registrado: {work_key}")
        clave = f"conflict|{work_key}||"
        existentes = await self._repo.decisiones_existentes([clave])
        if existentes and existentes[clave] != decision:
            raise DecisionExistenteDistinta(
                f"ya hay decisión {existentes[clave]!r} para {work_key}; no se altera"
            )
        nuevas = [] if existentes else [{
            "decision_key": clave,
            "item_key": fila["item_key"],
            "decision_type": "conflict",
            "person_key": fila["person_key"],
            "work_key": work_key,
            "role_key": fila["role_key"],
            "decision": decision,
            "target_person_key": None,
            "attribution_status": fila["attribution_status"],
            "evidence_json": json.dumps(
                {"decision_mode": "individual", "batch": "CONFLICTOS",
                 "personas": [p.get("person_key") for p in fila.get("personas", [])],
                 "researcher_note": evidence or note},
                ensure_ascii=False,
            ),
            "notes": note,
            "decided_by": decided_by,
            "batch": "CONFLICTOS",
        }]
        insertadas = await self._repo.insertar_decisiones(nuevas) if apply else 0
        return {
            "work_key": work_key, "decision": decision,
            "ya_existente": bool(existentes), "insertadas": insertadas, "aplicado": apply,
        }

    async def materializar(
        self, preview: Preview, *, confirm: str, decided_by: str, apply: bool = False
    ) -> dict[str, Any]:
        """Convierte el preview en decisiones individuales (una por unidad). Idempotente."""
        if confirm != preview.hash():
            raise PreviewNoValidado(
                f"hash de confirmación no coincide con el preview (esperado {preview.hash()})"
            )
        tipo = "identity" if preview.unidad == "identity_cluster" else "conflict"
        filas = [
            {
                "decision_key": f"{tipo}|{filtro.get('work_key') or ''}|{filtro['person_key']}|"
                                f"{filtro.get('role_key') or ''}",
                "item_key": filtro["item_key"],
                "decision_type": tipo,
                "person_key": filtro["person_key"],
                "work_key": filtro.get("work_key"),
                "role_key": filtro.get("role_key"),
                "decision": preview.decision,
                "target_person_key": None,
                "attribution_status": None,
                "evidence_json": json.dumps(
                    {"decision_mode": preview.modo, "preview_hash": preview.hash(),
                     "batch": preview.batch, "criterio": preview.resumen.get("criterio")},
                    ensure_ascii=False,
                ),
                "notes": None,
                "decided_by": decided_by,
                "batch": preview.batch,
            }
            for filtro in preview.filas
        ]
        existentes = await self._repo.decisiones_existentes([f["decision_key"] for f in filas])
        distintas = [
            clave for clave, valor in existentes.items()
            if valor != preview.decision
        ]
        if distintas:
            raise DecisionExistenteDistinta(
                f"{len(distintas)} decisiones existentes con otro valor; no se alteran: {distintas[:3]}"
            )
        nuevas = [f for f in filas if f["decision_key"] not in existentes]
        insertadas = await self._repo.insertar_decisiones(nuevas) if apply else 0
        return {
            "batch": preview.batch, "preview_hash": preview.hash(), "unidades": len(filas),
            "ya_existentes": len(existentes), "nuevas": len(nuevas),
            "insertadas": insertadas, "aplicado": apply,
        }
