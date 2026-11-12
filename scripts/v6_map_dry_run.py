"""Simulación del mapeo V6: Representations/works_resources → Resource/File.

No escribe en la base de datos. Genera un informe JSON con los recuentos
previstos y los conflictos que bloquean el corte (ficheros compartidos, filas
sin representación, claves físicas sin resolver, Works sin Resource).

Uso:
    python scripts/v6_map_dry_run.py [--out var/v6-dry-run-report.json]
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pymysql
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _count(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    return int(cur.fetchone()["c"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulación del mapeo V6 (solo lectura).")
    parser.add_argument("--out", default="var/v6-dry-run-report.json")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["db"]
    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["name"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        counts = {
            "works": _count(cur, "SELECT COUNT(*) c FROM works"),
            "representations": _count(cur, "SELECT COUNT(*) c FROM representations"),
            "works_resources": _count(cur, "SELECT COUNT(*) c FROM works_resources"),
            "files": _count(cur, "SELECT COUNT(*) c FROM files"),
            "files_con_storage_key": _count(
                cur, "SELECT COUNT(*) c FROM files WHERE storage_key IS NOT NULL AND storage_key <> ''"
            ),
        }
        standalone_resources = _count(
            cur,
            "SELECT COUNT(*) c FROM works_resources "
            "WHERE works_resources_representation_id IS NULL",
        )
        planned_files = _count(
            cur,
            "SELECT COUNT(*) c FROM works_resources WHERE works_resources_file_id IS NOT NULL",
        )
        conflicts = {
            "filas_sin_representacion_existente": _count(
                cur,
                "SELECT COUNT(*) c FROM works_resources wr "
                "LEFT JOIN representations r ON r.id = wr.works_resources_representation_id "
                "WHERE wr.works_resources_representation_id IS NOT NULL AND r.id IS NULL",
            ),
            "filas_sin_fichero_ni_url": _count(
                cur,
                "SELECT COUNT(*) c FROM works_resources "
                "WHERE works_resources_file_id IS NULL "
                "AND (works_resources_url IS NULL OR TRIM(works_resources_url) = '')",
            ),
            "ficheros_compartidos": _count(
                cur,
                "SELECT COUNT(*) c FROM ("
                "  SELECT works_resources_file_id FROM works_resources "
                "  WHERE works_resources_file_id IS NOT NULL "
                "  GROUP BY works_resources_file_id HAVING COUNT(*) > 1"
                ") shared",
            ),
            "works_sin_recurso": _count(
                cur,
                "SELECT COUNT(*) c FROM works w "
                "WHERE NOT EXISTS (SELECT 1 FROM representations r "
                "  WHERE r.representations_works_id = w.id) "
                "AND NOT EXISTS (SELECT 1 FROM works_resources wr "
                "  WHERE wr.works_resources_work_id = w.id)",
            ),
            "ficheros_sin_clave_fisica": _count(
                cur,
                "SELECT COUNT(*) c FROM files f "
                "LEFT JOIN storage_locations sl ON sl.file_id = f.id "
                "WHERE (f.storage_key IS NULL OR f.storage_key = '') "
                "AND (sl.object_key IS NULL OR sl.object_key = '')",
            ),
        }
        works_sin_recurso = _count(
            cur,
            "SELECT COUNT(*) c FROM works w "
            "WHERE NOT EXISTS (SELECT 1 FROM representations r "
            "  WHERE r.representations_works_id = w.id) "
            "AND NOT EXISTS (SELECT 1 FROM works_resources wr "
            "  WHERE wr.works_resources_work_id = w.id)",
        )
        planned_resources = (
            counts["representations"] + standalone_resources + works_sin_recurso
        )
        samples = {
            "filas_sin_representacion": [
                row["id"]
                for row in _fetchall(
                    cur,
                    "SELECT wr.id FROM works_resources wr "
                    "LEFT JOIN representations r ON r.id = wr.works_resources_representation_id "
                    "WHERE wr.works_resources_representation_id IS NOT NULL AND r.id IS NULL "
                    "LIMIT 20",
                )
            ],
            "works_sin_recurso": [
                row["id"]
                for row in _fetchall(
                    cur,
                    "SELECT w.id FROM works w "
                    "WHERE NOT EXISTS (SELECT 1 FROM representations r "
                    "  WHERE r.representations_works_id = w.id) "
                    "AND NOT EXISTS (SELECT 1 FROM works_resources wr "
                    "  WHERE wr.works_resources_work_id = w.id) LIMIT 20",
                )
            ],
        }
    conn.close()

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "database": cfg["name"],
        "counts": counts,
        "planned": {
            "resources": planned_resources,
            "resources_desde_representations": counts["representations"],
            "resources_sin_representacion": standalone_resources,
            "resources_referencia": works_sin_recurso,
            "files": planned_files,
        },
        "conflicts": conflicts,
        "samples": samples,
        "notes": [
            "Solo lectura; no se ha escrito en la base de datos.",
            "Cada Representation se propone como un Resource.",
            "Cada fila de works_resources con file_id se propone como File del Resource de su Representation.",
            "Las filas sin representación se proponen como Resource independiente (puede tener File o URL).",
            "Los conflictos se reportan, no se resuelven automáticamente.",
        ],
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"planned": report["planned"], "conflicts": conflicts}, ensure_ascii=False, indent=2))
    print(f"Informe: {out}")


def _fetchall(cur, sql: str) -> list[dict]:
    cur.execute(sql)
    return list(cur.fetchall())


if __name__ == "__main__":
    main()
