from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymysql
from infrastructure.config import PROJECT_ROOT, Settings
from pymysql.cursors import DictCursor

BATCH_SIZE = 20
RECORD_LIMIT = 50000
OUTPUT_PREFIX = "json_personas_lote_"
OUTPUT_PATTERN = re.compile(r"json_personas_lote_\d{3}\.json")
EXCLUDED_COLUMNS = {
    "visible",
    "status",
    "merged_into",
    "merged_at",
    "source_system",
    "created_at",
    "updated_at",
    "biography_key_works",
    "biography_key_fact",
    "type",
    "attribution_note",
    "nationality",
}


def fetch_persons(settings: Settings) -> list[dict[str, Any]]:
    connection = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM `Persons`
                ORDER BY
                    CASE
                        WHEN `persons_visible` = 1
                         AND `persons_review_status` = 'reviewed' THEN 0
                        ELSE 1
                    END,
                    `persons_id`
                LIMIT %s
                """,
                (RECORD_LIMIT,),
            )
            return cursor.fetchall()
    finally:
        connection.close()


def filtered_persons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered_rows = []
    for row in rows:
        filtered_row = {}
        for column, value in row.items():
            name = column.removeprefix("persons_")
            if (
                name.startswith(("review_", "merged_"))
                or name in EXCLUDED_COLUMNS
                or name.endswith("_nationality")
            ):
                continue
            filtered_row[column] = value
        filtered_rows.append(filtered_row)
    return filtered_rows


def json_value(value: Any) -> str | int | float:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    raise TypeError(f"Tipo no serializable a JSON: {type(value).__name__}")


def write_batches(rows: list[dict[str, Any]], output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_count = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    expected_files: set[str] = set()

    for batch_index in range(batch_count):
        filename = f"{OUTPUT_PREFIX}{batch_index + 1:03}.json"
        expected_files.add(filename)
        batch = rows[batch_index * BATCH_SIZE : (batch_index + 1) * BATCH_SIZE]
        output_path = output_dir / filename
        temporary_path = output_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(batch, ensure_ascii=False, separators=(",", ":"), default=json_value),
            encoding="utf-8",
        )
        temporary_path.replace(output_path)

    for path in output_dir.iterdir():
        if OUTPUT_PATTERN.fullmatch(path.name) and path.name not in expected_files:
            path.unlink()

    return batch_count


def main() -> None:
    settings = Settings()
    rows = filtered_persons(fetch_persons(settings))
    batch_count = write_batches(rows, PROJECT_ROOT / "data")
    print(f"Exportados {len(rows)} registros en {batch_count} lotes de hasta {BATCH_SIZE}.")


if __name__ == "__main__":
    main()
