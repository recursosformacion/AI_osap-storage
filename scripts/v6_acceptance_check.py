"""Validación de aceptación V6 sobre la copia de desarrollo.

Solo lectura. Comprueba invariantes Work→Resource→File, claves físicas, SHA,
URL-only y cuentas. Los Files huérfanos (sin Resource) se reportan como
excluidos, no como fallo del catálogo.

Uso:
    python scripts/v6_acceptance_check.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pymysql
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _count(cur, sql: str) -> int:
    cur.execute(sql)
    return int(cur.fetchone()["c"])


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["db"]
    conn = pymysql.connect(
        host=cfg["host"], port=int(cfg["port"]), user=cfg["user"],
        password=cfg["password"], database=cfg["name"], charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    checks = {
        "works_without_resource": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM works w WHERE NOT EXISTS "
            "(SELECT 1 FROM resources r WHERE r.work_id = w.id)",
        ),
        "resources_without_work": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM resources r LEFT JOIN works w ON w.id = r.work_id "
            "WHERE w.id IS NULL",
        ),
        "files_excluded_no_resource": _count(
            conn.cursor(), "SELECT COUNT(*) c FROM files WHERE resource_id IS NULL"
        ),
        "files_with_missing_resource": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM files f LEFT JOIN resources r ON r.id = f.resource_id "
            "WHERE f.resource_id IS NOT NULL AND r.id IS NULL",
        ),
        "files_without_storage_key": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM files WHERE storage_key IS NULL OR storage_key = ''",
        ),
        "storage_key_mismatches": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM files f WHERE f.resource_id IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM storage_locations sl WHERE sl.file_id = f.id "
            "AND sl.object_key = f.storage_key)",
        ),
        "duplicate_sha_groups": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM (SELECT sha256 FROM files WHERE sha256 IS NOT NULL "
            "GROUP BY sha256 HAVING COUNT(*) > 1) d",
        ),
        "url_only_resources": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM resources r WHERE r.external_url IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM files f WHERE f.resource_id = r.id)",
        ),
        "reference_resources": _count(
            conn.cursor(), "SELECT COUNT(*) c FROM resources WHERE kind = 'reference'"
        ),
        "resources_from_representation": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM resources WHERE legacy_kind = 'representation'",
        ),
        "resources_from_works_resource": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM resources WHERE legacy_kind = 'works_resource'",
        ),
        "works_with_reference_resource": _count(
            conn.cursor(),
            "SELECT COUNT(*) c FROM works WHERE reference_resource_id IS NOT NULL",
        ),
    }
    counts = {
        table: _count(conn.cursor(), f"SELECT COUNT(*) c FROM {table}")
        for table in ("works", "resources", "files", "works_resources", "representations")
    }
    conn.close()

    hard_failures = {
        key: value
        for key, value in checks.items()
        if key
        in {
            "works_without_resource",
            "resources_without_work",
            "files_with_missing_resource",
            "files_without_storage_key",
            "storage_key_mismatches",
        }
        and value
    }
    report = {
        "counts": counts,
        "checks": checks,
        "status": "FAIL" if hard_failures else "PASS",
        "hard_failures": hard_failures,
        "note": (
            "files_excluded_no_resource son capturas de administración excluidas del "
            "catálogo V6 (no se borran de R2). duplicate_sha_groups es informativo: SHA no "
            "es identidad."
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if hard_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
