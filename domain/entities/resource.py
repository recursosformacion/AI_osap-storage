"""Recurso V6: material concreto bajo una Work (edición, arreglo, grabación…).

Un Resource pertenece siempre a una Work y puede existir sin File (URL externa,
material pendiente de descarga o referencia). Los ficheros físicos (File) se
relacionan 1:N desde el repositorio; no se guardan aquí como identidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ResourceKind(StrEnum):
    SCORE = "score"
    PARTS = "parts"
    RECORDING = "recording"
    MIDI = "midi"
    REFERENCE = "reference"
    OTHER = "other"


class ResourceVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    PENDING = "pending"


@dataclass
class Resource:
    """Material V6 asociado a una Work.

    `source_system`/`external_id`/`external_url` identifican la procedencia del
    material (PDMX, CPDL, IMSLP, usuario…). La licencia describe este Resource,
    no la Work.
    """

    work_id: int
    kind: ResourceKind = ResourceKind.SCORE
    title: str | None = None
    source_system: str | None = None
    external_id: str | None = None
    external_url: str | None = None
    license: str | None = None
    rights_holder: str | None = None
    is_reference: bool = False
    visibility: ResourceVisibility = ResourceVisibility.PUBLIC
    metadata: dict[str, Any] = field(default_factory=dict)
    created_by: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.work_id <= 0:
            raise ValueError("resource.work_id debe ser positivo")
        if self.id is not None and self.id <= 0:
            raise ValueError("resource.id debe ser positivo")
        if self.kind is ResourceKind.REFERENCE:
            # Una referencia es un Resource sin material propio.
            self.is_reference = True

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)
