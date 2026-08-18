#!/usr/bin/env python
"""Ingestor en storage: lleva la respuesta de APP a la tabla de proveedores (simulado).

Lee el fichero de respuestas de APP (salida de `simulate_storage_call.py`) y, por cada
obra, emite una fila por proveedor con la evidencia de resolución, escribiéndola en
`provider_results.jsonl` (tabla `provider_results` SIMULADA — luego se conecta a una real).

Uso:
    python scripts/ingest_app_responses.py --in ../osap-api/script/storage_responses.json \
        [--out provider_results.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _provider_rows(response: dict[str, object]) -> list[dict[str, object]]:
    work_id = response.get("id")
    data = response.get("data") or {}
    status = response.get("status")
    rows: list[dict[str, object]] = []
    results = data.get("results") if isinstance(data, dict) else []
    if not isinstance(results, list):
        return rows
    for item in results:
        if not isinstance(item, dict):
            continue
        resolved = item.get("resolved") or {}
        composer = resolved.get("composer") or {}
        # Evidencia por proveedor
        for ev in item.get("evidence") or []:
            if not isinstance(ev, dict) or ev.get("kind") != "universe_match":
                continue
            rows.append(
                {
                    "work_id": work_id,
                    "provider": ev.get("provider"),
                    "item_id": item.get("id"),
                    "work_status": item.get("status"),
                    "confidence": item.get("confidence"),
                    "composer": composer.get("name") if composer else None,
                    "provider_confidence": ev.get("confidence"),
                    "session_status": status,
                }
            )
    return rows


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("provider_results.jsonl"))
    args = parser.parse_args()

    responses = json.loads(args.input.read_text(encoding="utf-8"))
    out = args.out.open("a", encoding="utf-8")
    total = 0
    for resp in responses:
        for row in _provider_rows(resp):
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            total += 1
    out.close()
    print(f"Filas de proveedor escritas: {total} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
