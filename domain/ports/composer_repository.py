"""Compatibilidad: `ComposerRepository` → `PersonRepository`.

El puerto canónico es ahora `PersonRepository` (`domain/ports/person_repository.py`).
"""

from __future__ import annotations

from domain.ports.person_repository import PersonRepository as ComposerRepository

__all__ = ["ComposerRepository"]
