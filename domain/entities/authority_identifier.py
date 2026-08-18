from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class AuthorityEntityType:
    """Tipo de entidad a la que se asocia el identificador de autoridad."""

    WORK = "work"
    COMPOSER = "composer"  # persona/compositor


class AuthorityScheme:
    """Esquemas de identificador de autoridad normalizados y consultables."""

    WIKIDATA = "wikidata"
    ISNI = "isni"
    VIAF = "viaf"
    LCCN = "lccn"
    MUSICBRAINZ = "musicbrainz"
    ISWC = "iswc"
    IPI = "ipi"


@dataclass
class AuthorityIdentifier:
    """Identificador de autoridad asociado a una entidad (obra o compositor).

    No es una copia de la base de autoridad: es el identificador (y su proveniencia)
    que el sistema usa para consumir identidades en vez de strings de compositores.
    """

    entity_type: str  # AuthorityEntityType.WORK | COMPOSER
    entity_id: str  # id de la obra o del compositor en Storage
    scheme: str  # AuthorityScheme.*
    value: str
    source: str = ""
    confidence: float = 0.0
    metadata: dict | None = None
    retrieved_at: datetime | None = None
    id: int | None = None
