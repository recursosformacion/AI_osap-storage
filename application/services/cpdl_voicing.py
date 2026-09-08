"""Normalización de `voicing` CPDL a términos buscables.

CPDL guarda `cpdl_pages.voicing` como JSON array, p. ej.:
    ["4", "SATB"]
    ["4", "SATB, STTB, AATB, ATTB"]
    ["1", "Solo Soprano"]
    ["4 or 5", "SATB, SAATB, SATTB", "add=... {{Vcat..."]

El primer elemento suele ser el número de voces pero es informal (rangos, texto) y no
es fiable. Los voicings descriptivos van en los elementos siguientes, separados por coma.

Este módulo extrae SOLO tokens descriptivos normalizados (sin crear identidades nuevas):
- se descarta el elemento numérico y los restos de plantilla (`add=`, `{{...}}`);
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
# Token válido: debe contener letras y no empezar por dígito (descarta "4", "4 or 5"...).
_LETTERS = re.compile(r"[A-Za-z\u00c0-\u024f]")
# Separadores de varios voicings dentro del mismo elemento de la plantilla.
_SPLIT_RE = re.compile(r"\s*,\s*")
# Normalización de comparación: mayúsculas, un solo espacio, quita comillas y espacios
# sobrantes (se conservan puntos/guiones/slashes: "SATB.SATB", "S,T", "Solo Soprano").
_KEEP_RE = re.compile(r"[^A-Za-z0-9À-ÖØ-öø-ÿ .\-#&/+']")


def normalize_term(raw: str) -> str:
    """Canonicaliza un voicing para comparación exacta (sin tocar el dato CPDL)."""
    s = _TEMPLATE_NOISE.sub(" ", str(raw or "")).strip()
    s = _KEEP_RE.sub(" ", s)
    s = " ".join(s.split()).upper()
    return s.strip(" .-")


def is_useful_term(raw: str) -> bool:
    """Un término es buscable solo si describe voces (contiene letras y no empieza por nº)."""
    s = str(raw or "").strip()
    if not s:
        return False
    if "=" in s or "{{" in s or "}}" in s:
        return False
    if not _LETTERS.search(s):
        return False
    return not s[0].isdigit()


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
