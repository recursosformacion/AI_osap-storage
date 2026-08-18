from __future__ import annotations

import json
from datetime import UTC, datetime

from domain.entities.authority_identifier import AuthorityIdentifier

from infrastructure.db.connection import Database


def _row_to_identifier(row: dict) -> AuthorityIdentifier:
    metadata = row.get("metadata_json")
    if isinstance(metadata, str) and metadata:
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = None
    return AuthorityIdentifier(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        scheme=row["scheme"],
        value=row["value"],
        source=row.get("source") or "",
        confidence=float(row.get("confidence") or 0),
        metadata=metadata if isinstance(metadata, dict) else None,
        retrieved_at=row.get("retrieved_at"),
    )


class SqlAuthorityIdentifierRepository:
    """Implementación MySQL de `authority_identifiers`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(self, identifier: AuthorityIdentifier) -> AuthorityIdentifier:
        metadata = json.dumps(identifier.metadata, ensure_ascii=False) if identifier.metadata else None
        retrieved_at = identifier.retrieved_at or datetime.now(UTC)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO authority_identifiers "
                "(entity_type, entity_id, scheme, value, source, confidence, metadata_json, retrieved_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE value = VALUES(value), source = VALUES(source), "
                "confidence = VALUES(confidence), metadata_json = VALUES(metadata_json), "
                "retrieved_at = VALUES(retrieved_at)",
                (
                    identifier.entity_type,
                    identifier.entity_id,
                    identifier.scheme,
                    identifier.value,
                    identifier.source,
                    identifier.confidence,
                    metadata,
                    retrieved_at,
                ),
            )
        return (
            await self.get(identifier.entity_type, identifier.entity_id, identifier.scheme)
        ) or identifier

    async def get(self, entity_type: str, entity_id: str, scheme: str) -> AuthorityIdentifier | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM authority_identifiers "
                "WHERE entity_type = %s AND entity_id = %s AND scheme = %s",
                (entity_type, entity_id, scheme),
            )
            row = await cur.fetchone()
        return _row_to_identifier(dict(row)) if row else None

    async def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuthorityIdentifier]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM authority_identifiers "
                "WHERE entity_type = %s AND entity_id = %s ORDER BY scheme",
                (entity_type, entity_id),
            )
            rows = await cur.fetchall()
        return [_row_to_identifier(dict(r)) for r in rows]

    async def find_by_scheme_value(self, scheme: str, value: str) -> list[AuthorityIdentifier]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM authority_identifiers WHERE scheme = %s AND value = %s",
                (scheme, value),
            )
            rows = await cur.fetchall()
        return [_row_to_identifier(dict(r)) for r in rows]

    async def delete(self, entity_type: str, entity_id: str, scheme: str) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM authority_identifiers "
                "WHERE entity_type = %s AND entity_id = %s AND scheme = %s",
                (entity_type, entity_id, scheme),
            )
