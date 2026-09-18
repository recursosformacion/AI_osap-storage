"""Compatibilidad: `sql_composer_repository` → `sql_person_repository`.

La implementación canónica es ahora `infrastructure/repositories/sql_person_repository.py`.
Este módulo mantiene los nombres antiguos para no romper imports existentes.
"""

from __future__ import annotations

from infrastructure.repositories.sql_person_repository import (
    SqlComposerRepository,
    SqlPersonRepository,
)

__all__ = ["SqlComposerRepository", "SqlPersonRepository"]
