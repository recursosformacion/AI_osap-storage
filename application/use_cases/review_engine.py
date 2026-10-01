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


class ReviewEngine:
    def __init__(self, repo: SqlReviewRepository) -> None:
        self._repo = repo

    async def preview_tramo(
        self, tramo: str, decision: str, *, batch: str, role_key: str | None = None,
        limite: int = 5000, tamano_muestra: int = 5,
    ) -> Preview:
        """Prepara un lote de identidad: selección + muestra + excepciones + resumen."""
        if decision not in _DECISIONES_IDENTITY:
            raise ValueError(f"decisión de identidad inválida: {decision}")
        unidades = await self._repo.unidades_tramo(tramo, role_key, limite)
        if not unidades:
            raise LookupError(f"sin unidades para el tramo {tramo}")
        muestra = unidades[:tamano_muestra]
        excepciones = [
            {
                "item_key": u["item_key"], "person_key": u["person_key"],
                "nombres": json.loads(u["contexto_json"]).get("nombres_vistos", [])[:6],
                "obras": u["obras"],
            }
            for u in unidades
            if "colision_de_clave\": true" in str(u["contexto_json"])
            or "contaminated" in str(u["estados"])
            or "sanitized" in str(u["estados"])
        ]
        return Preview(
            batch=batch, modo=f"bulk:{tramo.upper()}", unidad="identity_cluster", decision=decision,
            filas=unidades, muestra=muestra, excepciones=excepciones,
            resumen={
                "unidades": len(unidades),
                "obras": sum(int(u["obras"]) for u in unidades),
                "roles": sorted({str(u["roles"] or "") for u in unidades}),
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
