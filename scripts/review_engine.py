"""CLI del motor de revisión humana (batch -> preview -> validación -> review_decisions).

Docstring/resumen (regla del repo): convierte una decisión humana de alto nivel en decisiones
individuales auditables en `review_decisions` (una por unidad). **No ejecuta nada sobre el catálogo**
(`works`, `persons`, `works_person_roles`, `work_attribution_audit` fuera de alcance).

Uso:
    python -m scripts.review_engine conflicts  --out preview_conflictos.json
    python -m scripts.review_engine preview --tramo A --decision accept --batch A-0001 --out preview_A.json
    python -m scripts.review_engine preview --tramo F --decision leave_unresolved --batch F-0001 --out preview_F.json
    python -m scripts.review_engine apply --preview preview_A.json --confirm <hash> --decided-by admin
    python -m scripts.review_engine apply --preview preview_A.json --confirm <hash> --decided-by admin --apply
    python -m scripts.review_engine decide --tipo identity --person "name:…" \
        --decision map_to_existing --target-person "viaf:…" --batch D-1 --decided-by admin --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from application.use_cases.review_engine import Preview, ReviewEngine
from infrastructure.config import Settings
from infrastructure.db.connection import Database
from infrastructure.repositories.sql_review_repository import SqlReviewRepository


def _cargar_preview(ruta: Path) -> Preview:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return Preview(
        batch=datos["batch"], modo=datos["modo"], unidad=datos["unidad"], decision=datos["decision"],
        filas=datos["filas"], muestra=datos.get("muestra", []), excepciones=datos.get("excepciones", []),
        resumen=datos.get("resumen", {}),
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p_conf = sub.add_parser("conflicts", help="preview de los conflictos persona↔atribución")
    p_conf.add_argument("--out", type=Path, required=True)

    p_prev = sub.add_parser("preview", help="preview de un lote de identidad (tramo A–F)")
    p_prev.add_argument("--tramo", required=True, help="tramo de identidad A–F (F = ambiguo)")
    p_prev.add_argument("--decision", required=True)
    p_prev.add_argument("--batch", required=True)
    p_prev.add_argument("--role", default=None)
    p_prev.add_argument("--limite", type=int, default=5000)
    p_prev.add_argument("--out", type=Path, required=True)

    p_apply = sub.add_parser("apply", help="materializa las decisiones de un preview validado")
    p_apply.add_argument("--preview", type=Path, required=True)
    p_apply.add_argument("--confirm", required=True)
    p_apply.add_argument("--decided-by", required=True)
    p_apply.add_argument("--apply", action="store_true", help="escribir en review_decisions")

    p_dec = sub.add_parser("decide", help="decisión individual: identidad, conflicto o atribución")
    p_dec.add_argument("--tipo", default="conflict", choices=("identity", "conflict", "attribution"))
    p_dec.add_argument("--work", default=None, help="work_key (conflict/attribution)")
    p_dec.add_argument("--person", default=None, help="person_key del clúster canónico (identity)")
    p_dec.add_argument("--target-person", default=None, help="person_key destino (identity: map_to_existing)")
    p_dec.add_argument(
        "--decision", required=True,
        help=(
            "identity: accept|map_to_existing|create_person|not_a_person|leave_unresolved · "
            "conflict: persona_gana|atribucion_gana|revisar_manual · "
            "attribution: anonymous|traditional|unknown|identified"
        ),
    )
    p_dec.add_argument("--batch", default=None, help="etiqueta de lote (identity; por defecto IDENTIDAD)")
    p_dec.add_argument("--decided-by", required=True)
    p_dec.add_argument("--note", default=None, help="nota del revisor")
    p_dec.add_argument("--evidence", default=None, help="evidencia/justificación (p. ej. fuente consultada)")
    p_dec.add_argument("--apply", action="store_true", help="escribir en review_decisions")

    p_cor = sub.add_parser("corregir", help="corrige una decisión conservando el historial")
    p_cor.add_argument("--decision-key", required=True)
    p_cor.add_argument("--decision", required=True, help="nueva decisión vigente")
    p_cor.add_argument("--decided-by", required=True)
    p_cor.add_argument("--reason", required=True, help="motivo de la corrección (obligatorio)")
    p_cor.add_argument("--evidence", default=None)
    p_cor.add_argument("--note", default=None)
    p_cor.add_argument("--apply", action="store_true", help="escribir (historial + decisión vigente)")

    args = parser.parse_args()
    settings = Settings()  # type: ignore[call-arg]
    engine = ReviewEngine(SqlReviewRepository(Database(settings)))

    if args.comando == "decide":
        if args.tipo == "identity":
            if not args.person:
                parser.error("--tipo identity exige --person")
            resultado = await engine.decidir_identidad(
                args.person, args.decision, decided_by=args.decided_by,
                target_person_key=args.target_person, note=args.note,
                evidence=args.evidence, batch=args.batch, apply=args.apply,
            )
        elif args.tipo == "attribution":
            if not args.work:
                parser.error("--tipo attribution exige --work")
            resultado = await engine.decidir_atribucion(
                args.work, args.decision, decided_by=args.decided_by, note=args.note,
                evidence=args.evidence, apply=args.apply,
            )
        else:
            if not args.work:
                parser.error("--tipo conflict exige --work")
            resultado = await engine.decidir_conflicto(
                args.work, args.decision, decided_by=args.decided_by, note=args.note,
                evidence=args.evidence, apply=args.apply,
            )
        print(json.dumps(resultado, ensure_ascii=False))
        return 0

    if args.comando == "corregir":
        resultado = await engine.corregir_decision(
            args.decision_key, args.decision, decided_by=args.decided_by, reason=args.reason,
            evidence=args.evidence, notes=args.note, apply=args.apply,
        )
        print(json.dumps(resultado, ensure_ascii=False))
        return 0

    if args.comando == "conflicts":
        preview = await engine.preview_conflictos()
        args.out.write_text(json.dumps({
            "batch": preview.batch, "modo": preview.modo, "unidad": preview.unidad, "decision": "",
            "hash": preview.hash(), "resumen": preview.resumen, "filas": preview.filas,
        }, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps(
            {"preview": str(args.out), "obras": preview.resumen["obras"], "hash": preview.hash()},
            ensure_ascii=False,
        ))
        return 0

    if args.comando == "preview":
        preview = await engine.preview_tramo(
            args.tramo, args.decision, batch=args.batch, role_key=args.role, limite=args.limite
        )
        args.out.write_text(json.dumps({
            "batch": preview.batch, "modo": preview.modo, "unidad": preview.unidad,
            "decision": preview.decision, "hash": preview.hash(), "resumen": preview.resumen,
            "muestra": preview.muestra, "excepciones": preview.excepciones, "filas": preview.filas,
        }, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps({
            "preview": str(args.out), "hash": preview.hash(), "resumen": preview.resumen,
            "muestra": [
                {"item_key": m["item_key"], "person_key": m["person_key"], "obras": m["obras"],
                 "nombres": json.loads(m["contexto_json"]).get("nombres_vistos", [])[:4]}
                for m in preview.muestra
            ],
            "excepciones": preview.excepciones[:5],
        }, ensure_ascii=False, indent=1, default=str))
        return 0

    preview = _cargar_preview(args.preview)
    resultado = await engine.materializar(
        preview, confirm=args.confirm, decided_by=args.decided_by, apply=args.apply
    )
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
