from __future__ import annotations

from typing import Protocol

from domain.entities.resolution import ResourceEvidence


class ResolutionSource(Protocol):
    """Evidencia de solo lectura para el resolutor (no escribe)."""

    async def load(self, work_id: int, *, candidate_limit: int = 50) -> list[ResourceEvidence]: ...
