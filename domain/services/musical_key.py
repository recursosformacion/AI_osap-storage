"""Extracción determinista de tonalidad desde texto libre.

Los títulos y los nombres importados mezclan la tonalidad con el resto del texto
("Prelude in D major", "B minor Jeremiah Ingalls", "Phrygian Mode D minor",
"ré majeur"). Este módulo localiza esos tramos y los canonicaliza al estilo de
`works_musical_key` (`D major`, `B♭ major`, `D minor (Phrygian)`), sin tocar la
base de datos.

Reglas:
- Se reconoce la letra de la nota (A–G), el accidental (♯/♭/#/b/sharp/flat), la
  calidad (major/minor y equivalentes en español, francés, italiano y alemán) y
  los modos eclesiásticos.
- La solfège (`in re mayor`) se traduce a letra, pero solo con calidad explícita:
  `sol` o `la` como palabras sueltas son demasiado ambiguas.
- Los tramos se devuelven con posiciones para que el llamador pueda retirarlos del
  texto; los solapamientos se resuelven a favor del tramo más largo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_QUALITY = (
    r"major|minor|maj\.?|min\.?|majeur|majeure|mineur|dur|moll|mayor|menor|maggiore|minore"
)
_ACCIDENTAL = r"#|♯|b|♭|sharp|flat"
_MODES = r"Dorian|Phrygian|Lydian|Mixolydian|Aeolian|Ionian|Locrian"
_SOLFEGE = r"do|re|ré|mi|fa|sol|la|si"

_MAJOR = {"major", "maj", "majeur", "majeure", "dur", "mayor", "maggiore"}
_MINOR = {"min", "minor", "mineur", "moll", "menor", "minore"}
_SOLFEGE_TO_KEY = {
    "do": "C", "re": "D", "ré": "D", "mi": "E", "fa": "F", "sol": "G", "la": "A", "si": "B",
}

_P_MODE_KEY = re.compile(
    rf"\b(?P<mode>(?i:{_MODES}))\s+(?i:mode)(?:\s+(?i:on|in))?\s*"
    rf"(?P<key>[A-G])?\s*(?P<acc>{_ACCIDENTAL})?"
    rf"(?:\s*(?P<qual>(?i:{_QUALITY})))?\b"
)
_P_MODE = re.compile(rf"\b(?P<mode>(?i:{_MODES}))\s+(?i:mode)\b")
_P_IN_SOLFEGE = re.compile(
    rf"\b(?i:in|en)\s+(?P<sol>(?i:{_SOLFEGE}))\s+(?P<qual>(?i:{_QUALITY}))\b"
)
_P_IN = re.compile(
    rf"\b(?i:in|en)\s+(?P<key>[A-G])\s*(?P<acc>{_ACCIDENTAL})?"
    rf"(?:\s*(?P<qual>(?i:{_QUALITY})))?\b"
)
_P_HYPHEN = re.compile(
    rf"\b(?P<key>[A-Ga-g])\s*(?P<acc>{_ACCIDENTAL})?\s*[-\u2010-\u2015]\s*"
    rf"(?P<qual>(?i:{_QUALITY}))\b"
)
_P_IN_HYPHEN_ACC = re.compile(
    rf"\b(?i:in|en)\s+(?P<key>[A-G])\s*[-\u2010-\u2015]\s*(?P<acc>sharp|flat)"
    rf"(?:\s*(?P<qual>(?i:{_QUALITY})))?\b",
    re.I,
)
_P_KEY_HYPHEN_ACC = re.compile(
    rf"\b(?P<key>[A-G])\s*[-\u2010-\u2015]\s*(?P<acc>sharp|flat)"
    rf"(?:\s*(?P<qual>(?i:{_QUALITY})))?\b",
    re.I,
)
_P_KEY_QUAL = re.compile(
    rf"\b(?P<key>[A-G])\s*(?P<acc>{_ACCIDENTAL})?\s+(?P<qual>(?i:{_QUALITY}))\b"
)


@dataclass(frozen=True)
class TonalitySpan:
    """Tramo de texto que expresa una tonalidad."""

    start: int
    end: int
    key: str
    mode: str | None = None


def _quality(text: str | None) -> str | None:
    token = (text or "").lower().rstrip(".").strip()
    if not token:
        return None
    if token in _MAJOR:
        return "major"
    if token in _MINOR:
        return "minor"
    return None


def _accidental(text: str | None) -> str:
    token = (text or "").lower()
    if token in {"#", "♯", "sharp"}:
        return "♯"
    if token in {"b", "♭", "flat"}:
        return "♭"
    return ""


def _canonical(
    key: str | None, accidental: str | None, quality: str | None, mode: str | None
) -> str:
    if not key:
        return mode.title() if mode else ""
    note = key.upper() + _accidental(accidental)
    qual = _quality(quality)
    text = f"{note} {qual}" if qual else note
    return f"{text} ({mode.title()})" if mode else text


def _spans_from(pattern: re.Pattern[str], text: str) -> list[TonalitySpan]:
    spans: list[TonalitySpan] = []
    for match in pattern.finditer(text):
        groups = match.groupdict()
        mode = groups.get("mode")
        key = groups.get("key")
        if not key and not groups.get("qual") and not mode:
            continue
        value = _canonical(key, groups.get("acc"), groups.get("qual"), mode)
        if not value:
            continue
        spans.append(
            TonalitySpan(
                start=match.start(),
                end=match.end(),
                key=value,
                mode=mode.title() if mode else None,
            )
        )
    return spans


def find_tonalities(text: str | None) -> list[TonalitySpan]:
    """Tonalidades detectadas, sin solapamientos y en orden de aparición."""
    if not text:
        return []
    candidates: list[TonalitySpan] = []
    for pattern in (
        _P_MODE_KEY,
        _P_IN_HYPHEN_ACC,
        _P_IN,
        _P_HYPHEN,
        _P_KEY_HYPHEN_ACC,
        _P_KEY_QUAL,
        _P_MODE,
    ):
        for span in _spans_from(pattern, text):
            # "A Minor Bird" es un título: la nota La al inicio no es tonalidad.
            if pattern is _P_KEY_QUAL and span.start == 0 and span.key.startswith("A "):
                continue
            candidates.append(span)
    for match in _P_IN_SOLFEGE.finditer(text):
        sol = match.group("sol").lower()
        candidates.append(
            TonalitySpan(
                start=match.start(),
                end=match.end(),
                key=_canonical(_SOLFEGE_TO_KEY[sol], None, match.group("qual"), None),
            )
        )
    ordered = sorted(candidates, key=lambda item: (item.start, -(item.end - item.start)))
    out: list[TonalitySpan] = []
    for span in ordered:
        if any(span.start < kept.end and kept.start < span.end for kept in out):
            continue
        out.append(span)
    return sorted(out, key=lambda item: item.start)


def strip_tonalities(text: str | None) -> tuple[str, list[TonalitySpan]]:
    """Texto sin los tramos de tonalidad + las tonalidades encontradas."""
    raw = text or ""
    spans = find_tonalities(raw)
    cleaned = raw
    for span in reversed(spans):
        cleaned = cleaned[: span.start] + " " + cleaned[span.end:]
    return re.sub(r"\s+", " ", cleaned).strip(), spans


def join_tonalities(spans: list[TonalitySpan] | tuple[TonalitySpan, ...]) -> str | None:
    """Tonalidades en el formato del catálogo: `D major, B minor`."""
    values: list[str] = []
    for span in spans:
        if span.key not in values:
            values.append(span.key)
    return ", ".join(values) if values else None
