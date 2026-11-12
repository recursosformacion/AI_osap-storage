"""Vocabulario de instrumentos para extracción de metadatos.

Convierte las filas de `instruments` (código, nombre inglés/español, alias,
códigos IMSLP) en un buscador determinista de términos. El vocabulario se inyecta
desde la capa de infraestructura: este módulo no accede a la base de datos.

La comparación ignora mayúsculas, acentos y puntuación, y exige límites de palabra
para que `flauta` no case dentro de otra palabra y `bass` no case dentro de
`contrabass` (para eso están los alias explícitos del vocabulario).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

_MIN_TERM_LENGTH = 3
_PUNCT = re.compile(r"[^0-9a-z]+")


@dataclass(frozen=True)
class InstrumentTerm:
    code: str
    label: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstrumentMatch:
    code: str
    label: str
    term: str
    start: int
    end: int


def normalize_term(text: str | None) -> str:
    """Clave de comparación: minúsculas, sin acentos ni puntuación."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _PUNCT.sub(" ", ascii_text.casefold()).strip()


def _as_list(value: Any) -> list[str]:
    """Alias/IMSLP pueden llegar como JSON, lista o texto separado por comas."""
    if not value:
        return []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except ValueError:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [str(item) for item in parsed if str(item).strip()] if isinstance(parsed, list) else []
    return [part.strip() for part in text.split(",") if part.strip()]


class InstrumentVocabulary:
    """Buscador de instrumentos construido a partir de filas del catálogo."""

    def __init__(self, terms: Iterable[InstrumentTerm]) -> None:
        indexed: dict[str, InstrumentTerm] = {}
        for term in terms:
            for candidate in (term.label, *term.aliases):
                key = normalize_term(candidate)
                if len(key) < _MIN_TERM_LENGTH:
                    continue
                indexed.setdefault(key, term)
        self._terms = tuple(
            sorted(indexed.items(), key=lambda item: (-len(item[0]), item[0]))
        )

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]]) -> InstrumentVocabulary:
        terms: list[InstrumentTerm] = []
        for row in rows:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            label = str(row.get("name_es") or row.get("name_en") or code).strip()
            aliases = tuple(
                dict.fromkeys(
                    [
                        *_as_list(row.get("aliases")),
                        *_as_list(row.get("imslp_codes")),
                        str(row.get("name_en") or "").strip(),
                        code,
                    ]
                )
            )
            terms.append(InstrumentTerm(code=code, label=label or code, aliases=aliases))
        return cls(terms)

    def __bool__(self) -> bool:
        return bool(self._terms)

    def __len__(self) -> int:
        return len(self._terms)

    def find(self, text: str | None) -> list[InstrumentMatch]:
        """Coincidencias sin solapamiento, en orden de aparición."""
        key = normalize_term(text)
        if not key:
            return []
        found: list[InstrumentMatch] = []
        taken: list[tuple[int, int]] = []
        codes: set[str] = set()
        for term_key, term in self._terms:
            if term.code in codes:
                continue
            start = key.find(term_key)
            while start != -1:
                end = start + len(term_key)
                if (
                    (start == 0 or key[start - 1] == " ")
                    and (end == len(key) or key[end] == " ")
                    and not any(start < t_end and t_start < end for t_start, t_end in taken)
                ):
                    found.append(
                        InstrumentMatch(
                            code=term.code, label=term.label, term=term_key,
                            start=start, end=end,
                        )
                    )
                    taken.append((start, end))
                    codes.add(term.code)
                    break
                start = key.find(term_key, start + 1)
        return sorted(found, key=lambda item: item.start)
