from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from infrastructure.config import Settings
from infrastructure.db.connection import Database

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


async def migrate(db: Database) -> None:
    """Aplica las migraciones SQL pendientes, de forma idempotente."""
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    name VARCHAR(255) NOT NULL,
                    applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_schema_migrations_name (name)
                ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
                """
        )
        await cur.execute("SELECT name FROM schema_migrations")
        applied = {row["name"] for row in await cur.fetchall()}

    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if sql_file.name in applied:
            continue
        statements = [stmt.strip() for stmt in sql_file.read_text(encoding="utf-8").split(";") if stmt.strip()]
        async with db.connection() as conn, conn.cursor() as cur:
            for stmt in statements:
                await cur.execute(stmt)
            await cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (sql_file.name,))
        logger.info("applied migration %s", sql_file.name)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate(Database(Settings())))  # type: ignore[call-arg]


if __name__ == "__main__":
    main()
