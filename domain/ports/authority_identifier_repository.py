from __future__ import annotations

from typing import Protocol

from domain.entities.authority_identifier import AuthorityIdentifier


class AuthorityIdentifierRepository(Protocol):
    """Acceso a identificadores de autoridad por entidad y por esquema.

    El resto del sistema consume identidades (entity_id + scheme → value), no strings.
    """

    async def upsert(self, identifier: AuthorityIdentifier) -> AuthorityIdentifier: ...

    async def get(self, entity_type: str, entity_id: str, scheme: str) -> AuthorityIdentifier | None: ...

    async def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuthorityIdentifier]: ...

    async def find_by_scheme_value(self, scheme: str, value: str) -> list[AuthorityIdentifier]: ...

    async def delete(self, entity_type: str, entity_id: str, scheme: str) -> None: ...

    async def count_by_source(self, source: str) -> int: ...
