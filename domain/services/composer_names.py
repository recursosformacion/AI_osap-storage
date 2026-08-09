from __future__ import annotations

import re
import unicodedata

_SEPARATOR = re.compile(r"\s+")


def normalize_composer_name(name: str | None) -> str:
    """Normaliza un nombre de compositor para búsqueda determinista de alias.

    Convergencias aplicadas (sin tocar el nombre canónico original):
    - minúsculas;
    - eliminación de signos diacríticos (acentos, cedillas...);
    - eliminación de puntuación habitual (., , ; : ' " · - _);
    - colapso de espacios repetidos.

    Ejemplos que convergen al mismo resultado:
    "W. A. Mozart", "w. a. mozart", "W A Mozart" -> "w a mozart".
    """
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    for punct in (".", ",", ";", ":", "'", '"', "·", "´", "`", "-", "_", "(", ")"):
        text = text.replace(punct, " ")
    text = _SEPARATOR.sub(" ", text)
    return text.strip()
