"""Canonicalización de códigos de `ensembles` (formaciones vocales).

Reglas (una sola fuente para importer y mantenimiento):
- Los **espacios** son formato intra-formación: `SA T B` == `SATB`.
- `.` `/` `-` `_` separan **multi-coro o secciones** y se canonizan a `.`:
  `SATB-SATB` == `SATB.SATB`.
- Un código que **no** es una formación de voces se normaliza como descriptivo
  (un solo espacio): `SOLO MEZZO-SOPRANO` -> `SOLO MEZZO SOPRANO`.

Nota clave: una cadena de letras puede ser **notación vocal válida** (SATB, AATTB…);
nunca se clasifica como basura por estar compuesta de letras.
"""

from __future__ import annotations

import re

_TOKENS = ["BAR", "MZ", "TR", "CT", "S", "A", "T", "B", "C", "V"]
_SEP_SPLIT = re.compile(r"[./\-_]+")
_WS = re.compile(r"\s+")
# Vacío, con plantilla o con dígitos -> no es un conjunto de voces.
_NOISE = re.compile(r"(\{\{|\}\}|=|\d)")


def is_voice_block(text: str) -> bool:
    """True si el texto se compone íntegramente de símbolos de voz (BAR, S, A...)."""
    if not text or _NOISE.search(text):
        return False
    i = 0
    while i < len(text):
        for token in _TOKENS:
            if text.startswith(token, i):
                i += len(token)
                break
        else:
            return False
    return True


def canonical_code(code: str) -> str:
    """Canonicaliza un código de ensemble (formación vocal) o descriptivo."""
    upper = str(code or "").strip().upper()
    compact = _WS.sub("", upper)
    parts = [p for p in _SEP_SPLIT.split(compact) if p]
    if len(parts) > 1 and all(is_voice_block(p) for p in parts):
        return ".".join(parts)
    if is_voice_block(compact):
        return compact
    base = _SEP_SPLIT.sub(" ", upper)
    return " ".join(base.split())
