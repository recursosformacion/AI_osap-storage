"""Aplica el mapeo V6 en desarrollo: Representations/works_resources → Resource/File.

Idempotente: cada Resource conserva `legacy_kind`/`legacy_id` y las inserciones
comprueban que no exista. Sin `--apply` solo muestra los recuentos previstos.

Uso:
    python scripts/v6_apply_mapping.py
    python scripts/v6_apply_mapping.py --apply
"""

from __future__ import annotations

import argparse

import pymysql
import yaml

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


def _count(cur, sql: str) -> int:
    cur.execute(sql)
    return int(cur.fetchone()["c"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Mapeo V6 a Resource/File (idempotente).")
    parser.add_argument("--apply", action="store_true", help="Escribe los cambios.")
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
        autocommit=False,
        init_command="SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
    )
    statements: list[tuple[str, str]] = [
        (
            "resources_desde_representations",
            """
            INSERT INTO resources
              (work_id, kind, title, source_system, external_id, license,
               is_reference, visibility, metadata_json, legacy_kind, legacy_id)
            SELECT r.representations_works_id,
                   CASE LOWER(COALESCE(r.representations_type, ''))
                     WHEN 'parts' THEN 'parts'
                     WHEN 'recording' THEN 'recording'
                     WHEN 'midi' THEN 'midi'
                     ELSE 'score'
                   END,
                   r.representations_source_name,
                   r.representations_origin,
                   r.representations_origin_id,
                   r.representations_license,
                   0,
                   'public',
                   NULL,
                   'representation',
                   CAST(r.id AS CHAR)
            FROM representations r
            WHERE NOT EXISTS (
                SELECT 1 FROM resources x
                WHERE x.legacy_kind = 'representation'
                  AND x.legacy_id = CAST(r.id AS CHAR)
            )
            """,
        ),
        (
            "resources_sin_representacion",
            """
            INSERT INTO resources
              (work_id, kind, title, source_system, external_id, external_url,
               license, is_reference, visibility, metadata_json, legacy_kind, legacy_id)
            SELECT wr.works_resources_work_id,
                   CASE LOWER(COALESCE(wr.works_resources_type, ''))
                     WHEN 'parts' THEN 'parts'
                     WHEN 'recording' THEN 'recording'
                     WHEN 'midi' THEN 'midi'
                     ELSE 'score'
                   END,
                   wr.works_resources_name,
                   'legacy',
                   NULL,
                   wr.works_resources_url,
                   w.works_license,
                   0,
                   'public',
                   NULL,
                   'works_resource',
                   CAST(wr.id AS CHAR)
            FROM works_resources wr
            LEFT JOIN works w ON w.id = wr.works_resources_work_id
            WHERE wr.works_resources_representation_id IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM resources x
                WHERE x.legacy_kind = 'works_resource'
                  AND x.legacy_id = CAST(wr.id AS CHAR)
              )
            """,
        ),
        (
            "resources_referencia",
            """
            INSERT INTO resources
              (work_id, kind, title, source_system, is_reference, visibility,
               metadata_json, legacy_kind, legacy_id)
            SELECT w.id, 'reference', w.works_title, 'reference', 1, 'public',
                   NULL, 'work_reference', CAST(w.id AS CHAR)
            FROM works w
            WHERE NOT EXISTS (
                SELECT 1 FROM representations r
                WHERE r.representations_works_id = w.id
            )
              AND NOT EXISTS (
                SELECT 1 FROM works_resources wr
                WHERE wr.works_resources_work_id = w.id
            )
              AND NOT EXISTS (
                SELECT 1 FROM resources x
                WHERE x.legacy_kind = 'work_reference'
                  AND x.legacy_id = CAST(w.id AS CHAR)
              )
            """,
        ),
        (
            "files_resource_representacion",
            """
            UPDATE files f
            JOIN works_resources wr ON wr.works_resources_file_id = f.id
            JOIN resources r ON r.legacy_kind = 'representation'
                            AND r.legacy_id = CAST(wr.works_resources_representation_id AS CHAR)
            SET f.resource_id = r.id
            WHERE wr.works_resources_representation_id IS NOT NULL
              AND (f.resource_id IS NULL OR f.resource_id <> r.id)
            """,
        ),
        (
            "files_resource_standalone",
            """
            UPDATE files f
            JOIN works_resources wr ON wr.works_resources_file_id = f.id
            JOIN resources r ON r.legacy_kind = 'works_resource'
                            AND r.legacy_id = CAST(wr.id AS CHAR)
            SET f.resource_id = r.id
            WHERE wr.works_resources_representation_id IS NULL
              AND (f.resource_id IS NULL OR f.resource_id <> r.id)
            """,
        ),
        (
            "files_storage_key",
            """
            UPDATE files f
            JOIN (
                SELECT file_id, MIN(id) AS location_id
                FROM storage_locations
                WHERE object_key IS NOT NULL AND object_key <> ''
                GROUP BY file_id
            ) chosen ON chosen.file_id = f.id
            JOIN storage_locations sl ON sl.id = chosen.location_id
            SET f.storage_key = sl.object_key
            WHERE f.storage_key IS NULL OR f.storage_key = ''
            """,
        ),
    ]

    with conn.cursor() as cur:
        before = {
            "resources": _count(cur, "SELECT COUNT(*) c FROM resources"),
            "files_con_resource": _count(
                cur, "SELECT COUNT(*) c FROM files WHERE resource_id IS NOT NULL"
            ),
            "files_con_key": _count(
                cur,
                "SELECT COUNT(*) c FROM files WHERE storage_key IS NOT NULL AND storage_key <> ''",
            ),
        }
        print("antes:", before)
        if not args.apply:
            for name, _ in statements:
                print("pendiente:", name)
            print("Simulación; usa --apply para escribir.")
            return
        for name, sql in statements:
            cur.execute(sql)
            print(f"{name}: {cur.rowcount}")
            conn.commit()
        after = {
            "resources": _count(cur, "SELECT COUNT(*) c FROM resources"),
            "from_representation": _count(
                cur, "SELECT COUNT(*) c FROM resources WHERE legacy_kind='representation'"
            ),
            "standalone": _count(
                cur, "SELECT COUNT(*) c FROM resources WHERE legacy_kind='works_resource'"
            ),
            "reference": _count(
                cur, "SELECT COUNT(*) c FROM resources WHERE legacy_kind='work_reference'"
            ),
            "files_con_resource": _count(
                cur, "SELECT COUNT(*) c FROM files WHERE resource_id IS NOT NULL"
            ),
            "files_con_key": _count(
                cur,
                "SELECT COUNT(*) c FROM files WHERE storage_key IS NOT NULL AND storage_key <> ''",
            ),
            "files_sin_resource": _count(
                cur, "SELECT COUNT(*) c FROM files WHERE resource_id IS NULL"
            ),
        }
        print("después:", after)
    conn.close()


if __name__ == "__main__":
    main()
