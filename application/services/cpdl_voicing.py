"""Normalización de `voicing` CPDL a términos buscables.

CPDL guarda el voicing original como JSON array, p. ej.:
    ["4", "SATB"]
    ["4", "SATB, STTB, AATB, ATTB"]
    ["1", "Solo Soprano"]
    ["4", "4 equal voices"]
    ["4 or 5", "SATB, SAATB", "add=... {{Vcat..."]

El primer elemento suele ser el número de voces pero es informal (rangos, texto) y no
es fiable. El conteo puede ir pegado a la descripción en el mismo elemento
("4 equal voices"): ahí el conteo es prefijo, no término buscable.

Este módulo extrae SOLO tokens descriptivos normalizados (sin crear identidades nuevas):
- se descarta el elemento numérico, los rangos/conteos ("4", "4/5", "4 or 5", "4vv",
  "1 or more") y los restos de plantilla (`add=`, `{{...}}`);
- en un elemento con conteo prefijo se conserva la parte descriptiva
  ("4 equal voices" -> "EQUAL VOICES"), sin admitir puros números;
- cada elemento restante se parte por comas;
- el token normalizado se compara SIEMPRE como valor exacto (nunca substring), para que
  `SATB` no haga match con `SATB2`;
- la comparación es case-insensitive (normalizamos a mayúsculas);
- el dato original de CPDL nunca se modifica: estos tokens son derivados de búsqueda.
"""

from __future__ import annotations

import json
import re

# Cualquier resto de plantilla MediaWiki / parámetro nombrado descarta ese elemento.
_TEMPLATE_NOISE = re.compile(r"(\{\{|\}\}|=)")
# Token válido: debe contener letras y no quedarse en el conteo (descarta "4", "4/5"...).
_LETTERS = re.compile(r"[A-Za-z\u00c0-\u024f]")
# Separadores de varios voicings dentro del mismo elemento de la plantilla.
_SPLIT_RE = re.compile(r"\s*,\s*")
# Normalización de comparación: mayúsculas, un solo espacio, quita comillas y espacios
# sobrantes (se conservan puntos/guiones/slashes: "SATB.SATB", "S,T", "Solo Soprano").
_KEEP_RE = re.compile(r"[^A-Za-z0-9À-ÖØ-öø-ÿ .\-#&/+']")
# Conteo inicial de voces (informal): dígitos con rango/conector ("4", "4/5", "4 or 5",
# "3-4"), el modismo "N or more", y la unidad opcional ("4vv", "4 voices", "4 parts").
# Lo que queda tras quitarlo es la parte descriptiva ("4 equal voices" -> "equal voices").
_LEADING_COUNT = re.compile(
    r"^\s*\d+\s*"
    r"(?:(?:or|and|to)\s+more\b|(?:or|to|and|[-–—/.,+])\s*\d+\s*)*"
    r"(?:(?:voices?|parts?|vv|v)\s*"
    r"(?:(?:or|and|to)\s+more\b|(?:or|to|and|[-–—/.,+])\s*\d+\s*)*)?"
    r"\+?\s*",
    re.IGNORECASE,
)


def _descriptive(raw: str) -> str:
    """Parte descriptiva de un término: sin conteo inicial ni restos de plantilla."""
    s = _TEMPLATE_NOISE.sub(" ", str(raw or "")).strip()
    return _LEADING_COUNT.sub("", s, count=1).strip()


def normalize_term(raw: str) -> str:
    """Canonicaliza un voicing para comparación exacta (sin tocar el dato CPDL)."""
    s = _descriptive(raw)
    s = _KEEP_RE.sub(" ", s)
    s = " ".join(s.split()).upper()
    return s.strip(" .-")


def is_useful_term(raw: str) -> bool:
    """Un término es buscable solo si, sin su conteo, describe voces (tiene letras)."""
    s = str(raw or "").strip()
    if not s:
        return False
    if "=" in s or "{{" in s or "}}" in s:
        return False
    core = _descriptive(s)
    if not core or not _LETTERS.search(core):
        return False
    return bool(normalize_term(s))


def voicing_terms(voicing_json: str | None) -> list[str]:
    """Devuelve los términos buscables derivados del JSON de voicing CPDL (sin duplicados).

    Cada término se emite una sola vez por registro: la obra CPDL sigue siendo única.
    """
    if not voicing_json:
        return []
    try:
        raw = json.loads(voicing_json)
    except ValueError:
        return []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        for piece in _SPLIT_RE.split(item):
            if not is_useful_term(piece):
                continue
            term = normalize_term(piece)
            if term and term not in out:
                out.append(term)
    return out
