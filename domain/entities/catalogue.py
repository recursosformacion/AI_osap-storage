from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# Prefijo de un catálogo dentro de una referencia de obra:
# - "K. 15h" -> "K"   (letras + punto)
# - "BWV 846" -> "BWV" (letras + espacio + número)
# - "Hob. XVI:1" -> "Hob"
# Un único prefijo sin separador/número (p. ej. "A minor") NO se considera catálogo.
_PERIOD_RE = re.compile(r"^([A-Za-z]+)\.")
_NUM_RE = re.compile(r"^([A-Za-z]+)\s+\d")
# "Op" es genérico (muchos compositores) y no identifica a ninguno en particular.
GENERIC_PREFIXES = {"op", "opus", "no", "nos"}


def catalogue_prefix(reference: str | None) -> str | None:
    """Extrae la sigla/prefijo de un catálogo de una referencia de obra, o None.

    "K. 15h" -> "K"; "BWV 846" -> "BWV"; "Hob. XVI:1" -> "Hob"; "Op. 15" -> None (genérico).
    """
    text = (reference or "").strip()
    if not text:
        return None
    match = _PERIOD_RE.match(text) or _NUM_RE.match(text)
    if not match:
        return None
    prefix = match.group(1)
    if prefix.lower() in GENERIC_PREFIXES:
        return None
    return prefix


@dataclass
class Catalogue:
    """Un catálogo temático de obras de un compositor (Köchel, BWV, Hoboken, Ryom...)."""

    prefix: str
    composer: str
    catalogue_name: str
    creator: str
    ordering_criterion: str
    id: int | None = None
    created_at: datetime | None = None
