"""CLI del motor de revisión humana (batch -> preview -> validación -> review_decisions).

Docstring/resumen (regla del repo): convierte una decisión humana de alto nivel en decisiones
individuales auditables en `review_decisions` (una por unidad). **No ejecuta nada sobre el catálogo**
(`works`, `persons`, `works_person_roles`, `work_attribution_audit` fuera de alcance).

Uso:
    python -m scripts.review_engine conflicts  --out preview_conflictos.json
    python -m scripts.review_engine preview --tramo A --decision accept --batch A-0001 --out preview_A.json
    python -m scripts.review_engine apply --preview preview_A.json --confirm <hash> --decided-by admin
    python -m scripts.review_engine apply --preview preview_A.json --confirm <hash> --decided-by admin --apply
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

    p_prev = sub.add_parser("preview", help="preview de un lote de identidad")
    p_prev.add_argument("--tramo", required=True)
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

    p_dec = sub.add_parser("decide", help="decisión individual de un conflicto persona↔atribución")
    p_dec.add_argument("--work", required=True, help="work_key (p. ej. CPDL:14615)")
    p_dec.add_argument("--decision", required=True, choices=("persona_gana", "atribucion_gana", "revisar_manual"))
    p_dec.add_argument("--decided-by", required=True)
    p_dec.add_argument("--apply", action="store_true", help="escribir en review_decisions")

    args = parser.parse_args()
    settings = Settings()  # type: ignore[call-arg]
    engine = ReviewEngine(SqlReviewRepository(Database(settings)))

    if args.comando == "decide":
        resultado = await engine.decidir_conflicto(
            args.work, args.decision, decided_by=args.decided_by, apply=args.apply
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
