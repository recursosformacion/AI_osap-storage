"""Parser determinista de los nombres de `works_person_import` (paso 1 de la reconciliación).

Los ficheros de origen (PDMX/CPDL) traen texto libre donde caben varias cosas:

- atribuciones no personales: ``anon.``, ``Traditional``, ``Misc tunes``, ``Desconocido``;
- personas con el rol embebido: ``Composed by X``, ``Arranged by Y``, ``Adap. Z``;
- varias personas/roles en una sola cadena: ``Composed by A Arranged by B``;
- nombres con fechas o ruido: ``Edward Patrick Crawford (1846-1912)``;
- basura: URLs, códigos, años sueltos.

Este módulo convierte cada cadena en 0..N `ParsedPerson` con su rol canónico de
`domain.services.person_roles` (o en una propuesta de atribución). No toca la BD: es pura y
testeable; la escritura la hará el script sobre la tabla de staging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from domain.services.person_roles import ROLE_IDS

Kind = Literal["person", "attribution", "junk"]

# Valores que NO son personas: son atribuciones (o ruido) y van como propuesta de atribución.
_NO_PERSONA: dict[str, str | None] = {
    "anonymous": "anonymous", "anon": "anonymous", "anon.": "anonymous",
    "anónimo": "anonymous", "anonimo": "anonymous", "anónima": "anonymous", "anonima": "anonymous",
    "desconhecido": "anonymous", "desconocido": "anonymous", "unknown": "anonymous",
    "autor unbekannt": "anonymous", "urheber unbekannt": "anonymous",
    "traditional": "traditional", "tradicional": "traditional", "trad.": "traditional",
    "trad": "traditional",
    "popular": "traditional", "volksweise": "traditional", "folk": "traditional",
    "misc tunes": None, "misc": None, "na": None, "n a": None, "a n": None, "": None, "-": None,
    "none": None, "null": None, "varios": None, "various": None, "various artists": None,
}

_ROLE_MARKERS: list[tuple[str, re.Pattern[str]]] = [
    (
        "arranger",
        re.compile(
            r"\b(?:arranged by|arrangement by|arranger\b|arr\.|arreglad[oa]s? por\b|arreglo de\b)",
            re.I,
        ),
    ),
    (
        "adapter",
        re.compile(
            r"\b(?:adapted by|adaption by|adaptation by|adap\.|adaptad[oa] por\b|adaptaci[oó]n de\b|"
            r"version by\b|versi[oó]n de\b)",
            re.I,
        ),
    ),
    ("transcriber", re.compile(r"\b(?:transcribed by|transcription by|transcri\w*|transcr\.)", re.I)),
    ("orchestrator", re.compile(r"\b(?:orchestrated by|orchestration by|orchestrat\w*|orquestad[oa] por\b)", re.I)),
    (
        "librettist",
        re.compile(r"\b(?:lyrics by|lyric by|words by|text by|letra de\b|letrista\b|texto de\b|tex\.)", re.I),
    ),
    ("editor", re.compile(r"\b(?:edited by|editor\b|revised by|revisad[oa] por\b|ed\.)", re.I)),
    ("composer", re.compile(r"\b(?:composed by|composer\b|music by|música de\b|música:|comp\.|composition by)", re.I)),
]
# Los ficheros de origen pegan palabras ("PADENAdapted", "GABRIELArranged"): se separa antes de parsear.
_GLUED_ROLE = re.compile(
    r"(?<=[A-Za-z])(?=(?:Arranged|Adapted|Transcribed|Orchestrated|Composed|Edited|Lyrics|Words|Music)\b)"
)
_SUFFIX_ROLE = re.compile(
    r"\(\s*(arranger|arr\.?|adapter|adap\.?|transcriber|transcr\.?|orchestrator|orch\.?|"
    r"editor|ed\.?|composer|comp\.?)\s*\)\s*$",
    re.I,
)
_SUFFIX_ROLE_KEYS = {
    "arr": "arranger", "arranger": "arranger", "adap": "adapter", "adapter": "adapter",
    "transcr": "transcriber", "transcriber": "transcriber", "orch": "orchestrator",
    "orchestrator": "orchestrator", "ed": "editor", "editor": "editor",
    "comp": "composer", "composer": "composer",
}
_SPLIT_PEOPLE = re.compile(r"\s*(?:;|/|&|\+|\band\b)\s*", re.I)
_CLEAN_NAME = re.compile(r"[\"'\[\]\(\)]")
_DATES = re.compile(r"\(?\b(1[0-9]{3}|20[0-2][0-9])\b[^)\]]*[\)\]]?|\[\s*1[0-9]{3}\s*[-–]\s*1[0-9]{3}\s*\]")
_URL = re.compile(r"(https?://\S+|www\.\S+)")
_XML = re.compile(r"<[^>]{1,40}>")
# Símbolos musicales de MuseScore incrustados: se elimina el elemento con su contenido.
_SYM = re.compile(r"<sym>.*?</sym>", re.S)
_GLUED_LOWER = re.compile(
    r"(?<=[A-Za-z])(?=(?:arr\.|arranged by|adapted by|transcribed by|orchestrated by|composed by|"
    r"edited by|lyrics by|words by|music by|with\b|from\b))\s*",
    re.I,
)
_EXPRESSION = re.compile(r"\bwith (spirit|feeling|vigour|vigor|energy|expression|soul|gusto)\b", re.I)
# Texto que describe procedencia/derivación, no autoría ("after X", "from Y", "based on Z").
_DERIVATION = re.compile(
    r"^\s*(after|based on|from|adapted from|as sung by|collected from|per the version of|"
    r"a version of|taken from)\b",
    re.I,
)
# Atribuciones no personales que pueden venir con coletilla: "trad Shetland", "anon. s. XIV".
_ATTRIBUTION_ANY = re.compile(
    r"\b(anon\.?|anonymous|anónim[oa]|anonim[oa]|desconocid[oa]|desconhecid[oa]|traditional|tradicional|"
    r"trad\.?|popular|volksweise|traditionnel)\b",
    re.I,
)


def _attribution_from_word(word: str) -> str | None:
    lowered = word.lower().rstrip(".")
    if lowered in _ATTRIBUTION_WORD_STATUS:
        return _ATTRIBUTION_WORD_STATUS[lowered]
    if lowered.startswith(("anon", "anónim", "anonim", "desconocid", "desconhecid")):
        return "anonymous"
    if lowered.startswith(("trad", "popular", "volksweise", "traditionnel")):
        return "traditional"
    return None
_ATTRIBUTION_WORD_STATUS = {
    "anon": "anonymous", "anonymous": "anonymous", "anónima": "anonymous", "anónimo": "anonymous",
    "anonima": "anonymous", "anonimo": "anonymous", "desconocido": "anonymous", "desconocida": "anonymous",
    "desconhecido": "anonymous", "traditional": "traditional", "tradicional": "traditional",
    "trad": "traditional", "popular": "traditional", "volksweise": "traditional",
    "traditionnel": "traditional",
}
_ROLE_SUFFIX_WORDS = re.compile(
    r"\b(arr|arranger|adapt|adapter|transcr|orch|ed|editor|composer|comp|music|lyrics|vocal|text)\b\.?",
    re.I,
)
_IMPORT_ROLE_TO_KEY = {"composer": "composer", "editor": "editor", "librettist": "librettist"}


@dataclass(frozen=True)
class ParsedPerson:
    name: str
    role_key: str
    evidence: str
    position: int = 0


@dataclass(frozen=True)
class ParsedRow:
    kind: Kind
    persons: list[ParsedPerson] = field(default_factory=list)
    attribution_status: str | None = None
    reason: str | None = None

def _looks_like_name(text: str) -> bool:
    cleaned = _CLEAN_NAME.sub(" ", text).strip(" .,-")
    if not cleaned or len(cleaned) < 2 or len(cleaned) > 120:
        return False
    words = cleaned.split()
    if not 1 <= len(words) <= 6:
        return False
    if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", cleaned):
        return False
    if re.search(r"\d", cleaned):
        return False
    if cleaned.lower().strip(" .") in _NO_PERSONA:
        return False
    return not _ROLE_SUFFIX_WORDS.search(cleaned)


def _clean_person(text: str) -> str:
    out = _SYM.sub(" ", text or "")
    out = _XML.sub(" ", out)
    out = _URL.sub(" ", out)
    out = _EXPRESSION.sub(" ", out)
    out = _DATES.sub(" ", out)
    out = _ROLE_SUFFIX_WORDS.sub(" ", out)
    out = _CLEAN_NAME.sub(" ", out)
    out = re.sub(r"\s+", " ", out).strip(" .,-;")
    return out


def _extract_after(marker: re.Match[str], text: str) -> str:
    tail = text[marker.end(): marker.end() + 160]
    # Corta en el siguiente marcador de rol, separador fuerte o año.
    tail = re.split(r"\b(?:arranged by|adapted by|transcribed by|orchestrated by|lyrics by|text by|"
                    r"composed by|music by|composition by|ed(?:ited)?\.? by)\b|;|\||\b1[0-9]{3}\b",
                    tail, flags=re.I)[0]
    # Quita el conector que queda tras el marcador ("arr. by X").
    tail = re.sub(r"^\s*(?:by|de|por|:)\s+", "", tail, flags=re.I)
    return _clean_person(tail)


def parse_import_name(raw: str | None, import_role: str = "composer") -> ParsedRow:
    """Clasifica una fila de `works_person_import`."""
    text = (raw or "").strip()
    text = _SYM.sub(" ", text)
    text = _XML.sub(" ", text)
    text = _GLUED_ROLE.sub(" ", text)
    text = _GLUED_LOWER.sub(" ", text)
    lowered = re.sub(r"\s+", " ", text).lower().strip(" .")

    if lowered in _NO_PERSONA:
        status = _NO_PERSONA[lowered]
        if status is None:
            return ParsedRow(kind="junk", reason="valor sin significado de autoría")
        return ParsedRow(kind="attribution", attribution_status=status,
                         reason=f"texto de origen: {text[:120]}")

    # 1) Roles explícitos (posiblemente varios en la misma cadena), en el orden del texto.
    persons: list[ParsedPerson] = []
    for role_key, pattern in _ROLE_MARKERS:
        for marker in pattern.finditer(text):
            candidate = _extract_after(marker, text)
            if _looks_like_name(candidate):
                persons.append(
                    ParsedPerson(name=candidate, role_key=role_key,
                                 evidence=f"rol explícito en el texto: {text[:120]}",
                                 position=marker.start())
                )

    # 1b) Atribución no personal, sola o acompañada de personas ("traditional carol arr. X").
    inline_attribution: str | None = None
    inline_match = _ATTRIBUTION_ANY.search(text)
    if inline_match:
        inline_attribution = _attribution_from_word(inline_match.group(1))
        rest = (text[: inline_match.start()] + " " + text[inline_match.end():]).strip(" .,;")
        if not persons and rest and _DERIVATION.match(rest) is None:
            return ParsedRow(kind="attribution", attribution_status=inline_attribution,
                             reason=f"atribución con coletilla: {text[:120]}")

    if persons:
        return ParsedRow(kind="person", persons=_dedupe(persons), attribution_status=inline_attribution,
                         reason="con atribución no personal asociada" if inline_attribution else None)

    # 2) Texto de procedencia/derivación sin autoría propia: "after Chief F. O'Neill", "from X".
    if _DERIVATION.match(text):
        return ParsedRow(kind="junk", reason=f"procedencia derivada, no autoría: {text[:120]}")

    # 3) Sufijo entre paréntesis: "Koji Kondo / xMrPianox (Arranger)".
    suffix = _SUFFIX_ROLE.search(text)
    if suffix:
        role_key = _SUFFIX_ROLE_KEYS.get(suffix.group(1).lower().rstrip("."), "composer")
        base = _SUFFIX_ROLE.sub(" ", text)
        parts = [p for p in (_clean_person(part) for part in _SPLIT_PEOPLE.split(base)) if p]
        if parts and all(_looks_like_name(p) for p in parts):
            import_key = _IMPORT_ROLE_TO_KEY.get(import_role, "composer")
            found = [
                ParsedPerson(p, role_key if index == len(parts) - 1 else import_key,
                             f"sufijo de rol en el texto: {text[:120]}")
                for index, p in enumerate(parts)
            ]
            return ParsedRow(kind="person", persons=_dedupe(found))

    # 4) Varias personas sin rol explícito.
    parts = [p for p in (_clean_person(part) for part in _SPLIT_PEOPLE.split(text)) if p]
    if len(parts) > 1 and all(_looks_like_name(p) for p in parts):
        role_key = _IMPORT_ROLE_TO_KEY.get(import_role, "composer")
        return ParsedRow(
            kind="person",
            persons=_dedupe([ParsedPerson(p, role_key, f"varias personas en el texto: {text[:120]}") for p in parts]),
        )

    # 5) Una sola persona.
    candidate = _clean_person(text)
    if _looks_like_name(candidate):
        role_key = _IMPORT_ROLE_TO_KEY.get(import_role, "composer")
        return ParsedRow(kind="person", persons=[ParsedPerson(candidate, role_key, f"nombre simple: {text[:120]}")])

    return ParsedRow(kind="junk", reason=f"no parseable: {text[:120]}")


def _dedupe(persons: list[ParsedPerson]) -> list[ParsedPerson]:
    ordered = sorted(persons, key=lambda person: person.position)
    seen: set[tuple[str, str]] = set()
    out: list[ParsedPerson] = []
    for person in ordered:
        key = (person.name.lower(), person.role_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(person)
    return out


def role_id_for(role_key: str) -> int | None:
    """Id de `roles` para una clave canónica (None si no aplica)."""
    return ROLE_IDS.get(role_key)
