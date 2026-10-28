"""Crea representaciones para recursos MXL y guarda sus metadatos extraidos.

Cada `works_resources` MXL sin representacion crea una fila en `representations` (origen pdmx)
y otra en `representation_metadata` con titulo, instrumentacion, ensemble, partes, compases,
tonalidad, tempo, letra, creadores y derechos. Enlaza el recurso con la representacion.

Uso dev:
    .venv\\Scripts\\python.exe scripts/populate_mxl_representations.py --limit 100
    .venv\\Scripts\\python.exe scripts/populate_mxl_representations.py --limit 0 --apply
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "data" / "mxl_metadata" / "proposals_20261027.json"


def _db():
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    if conf.get("host") not in {"127.0.0.1", "localhost"}:
        raise SystemExit("rechazado: host no local")
    return pymysql.connect(
        host=conf["host"], port=conf["port"], user=conf["user"], password=conf["password"],
        database=conf["name"], charset="utf8mb4", cursorclass=DictCursor,
    )


def _json(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    return json.dumps(value, ensure_ascii=False)


def _license(value: str | None) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:120] or "PDMX"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    proposals = json.loads(args.file.read_text(encoding="utf-8"))
    if args.limit:
        proposals = proposals[args.offset : args.offset + args.limit]
    conn = _db()
    created = linked = skipped = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, works_resources_work_id work_id, works_resources_name name "
                "FROM works_resources WHERE LOWER(works_resources_type) IN ('mxl','musicxml') "
                "AND works_resources_representation_id IS NULL"
            )
            resources: dict[tuple[int, str], int] = {
                (int(r["work_id"]), str(r["name"])): int(r["id"]) for r in cur.fetchall()
            }
            for proposal in proposals:
                path = Path(str(proposal.get("file") or ""))
                resource_id = resources.get((int(proposal["work_id"]), path.name))
                if resource_id is None:
                    skipped += 1
                    continue
                if args.apply:
                    cur.execute(
                        "INSERT INTO representations "
                        "(representations_works_id, representations_origin, representations_origin_id, "
                        "representations_type, representations_source_name, representations_license, "
                        "representations_ensemble_code) "
                        "VALUES (%s, 'pdmx', %s, 'score', %s, %s, %s)",
                        (
                            int(proposal["work_id"]),
                            path.name[:191],
                            path.name,
                            _license(proposal.get("rights")),
                            (proposal.get("ensemble_guess") or None),
                        ),
                    )
                    representation_id = int(cur.lastrowid)
                    cur.execute(
                        "INSERT INTO representation_metadata "
                        "(representation_id, xml_title, instrumentation, ensemble, parts_count, measures, "
                        "notes, musical_keys, time_signatures, tempo, has_lyrics, creators, source, rights, "
                        "software, encoding_date, raw) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            representation_id,
                            proposal.get("xml_title"),
                            _json(proposal.get("instrumentation")),
                            proposal.get("ensemble_guess"),
                            proposal.get("parts_count"),
                            proposal.get("measures"),
                            proposal.get("notes"),
                            _json(proposal.get("keys")),
                            _json(proposal.get("time_signatures")),
                            proposal.get("tempo"),
                            proposal.get("has_lyrics"),
                            _json(proposal.get("creators")),
                            proposal.get("source"),
                            proposal.get("rights"),
                            proposal.get("software"),
                            proposal.get("encoding_date"),
                            json.dumps(proposal, ensure_ascii=False),
                        ),
                    )
                    cur.execute(
                        "UPDATE works_resources SET works_resources_representation_id=%s "
                        "WHERE id=%s AND works_resources_representation_id IS NULL",
                        (representation_id, resource_id),
                    )
                    linked += 1
                created += 1
                if args.apply and created % 500 == 0:
                    conn.commit()
        if args.apply:
            conn.commit()
    finally:
        conn.close()
    print(f"propuestas={len(proposals)} representaciones_creadas={created} enlazadas={linked} omitidas={skipped}")
    print("BD actualizada" if args.apply else "DRY-RUN: usa --apply para escribir")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
