from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Representation:
    """Forma concreta de una obra: edición, versión, arreglo, transcripción, partitura…

    `origin`/`origin_id` identifican la representación en su fuente (pdmx: `work_key`;
    cpdl: `page_id:cpdlno`).
    """

    works_id: int
    origin: str = ""
    origin_id: str | None = None
    origin_cpdlno: int | None = None
    type: str = ""
    source_name: str | None = None
    license: str = ""
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Resource:
    """Fichero que materializa una representación (MXL, PDF, MIDI…).

    `file_id` apunta al fichero interno; `url` es la procedencia externa. Ambos opcionales:
    permite inventariar recursos sin descargarlos.
    """

    representation_id: int | None = None
    type: str = ""
    name: str = ""
    relative_path: str | None = None
    status: str = ""
    file_id: int | None = None
    url: str | None = None
    archive_id: int | None = None
    id: int | None = None
    work_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
