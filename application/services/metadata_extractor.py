"""Extractor unificado de metadatos desde el texto de origen de una obra.

Los catálogos externos (PDMX, CPDL, IMSLP) y los ficheros MuseScore mezclan en un
solo campo el título, el compositor, la formación, la tonalidad, el arreglista y
códigos de fuente. Este módulo separa esas piezas de forma determinista, sin IA y
sin tocar la base de datos:

- **personas** (compositor, arreglista, adaptador, transcriptor, orquestador,
  editor, letrista, traductor) reutilizando `import_person_parser`;
- **atribución no personal** (`anonymous`, `traditional`);
- **tonalidad** con `domain.services.musical_key`;
- **formaciones vocales** con `canonical_ensemble` (solo `VOICES`/`SPECIAL`);
- **instrumentos** con el vocabulario inyectado (`InstrumentVocabulary`);
- **códigos** de opus, catálogo y años;
- **título limpio** frente al texto crudo.

Decisión V6: la extracción es una *propuesta derivada*. No crea personas ni cambia
`works_title` por sí sola; el alta de Works/Resources decide qué campos acepta y
la limpieza de títulos existentes exige revisión, tabla de correspondencia y 301.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from application.services.import_person_parser import (
    parse_import_name,
    sanitize_person_name,
)
from application.services.instrument_vocabulary import InstrumentVocabulary
from domain.services.ensemble_canonical import (
    KIND_SPECIAL,
    KIND_VOICES,
    canonical_ensemble,
)
from domain.services.musical_key import TonalitySpan, find_tonalities, join_tonalities

_INVISIBLE = re.compile(r"[\u00a0\u1680\u2000-\u200a\u2028\u2029\u205f\u3000]")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff\u00ad]")
_SPACES = re.compile(r"\s+")
_SYM = re.compile(r"<sym>.*?</sym>", re.S)
_XML = re.compile(r"<[^>]{1,60}>")

# Expresiones de rol con o sin "by" ("arr. X", "transcribed by X", "guitar transcription by X").
_ROLE_PHRASE = re.compile(
    r"\b(?:composed|arranged|adapted|transcribed|orchestrated|edited|revised|translated|"
    r"lyrics|words|text|music|composition|transcription|arrangement|adaptation)\s+by\s+"
    r"[^;|()\[\]]{2,80}",
    re.I,
)
_SHORT_ROLE_PHRASE = re.compile(r"\b(?:arr|adap|transcr|orch|ed|comp)\.\s*[^;|()\[\]]{2,80}", re.I)
_PAREN_ROLE = re.compile(
    r"\((?P<text>[^()]{2,80}?(?:arr\.?|arranger|adap\.?|adapter|transcr\.?|transcriber|"
    r"orch\.?|orchestrator|ed\.?|editor|comp\.?|composer))\)",
    re.I,
)
_PARENTHESES = re.compile(r"\(([^()]{2,60})\)")
_FOR_PHRASE = re.compile(r"\bfor\s+([^,.;:()\[\]]{2,80})", re.I)
_INSTRUMENT_CONTEXT = re.compile(
    r"\b(?:(?:a|an|the)\s+)?"
    r"(piano|organ|guitar|violin|viola|cello|flute|clarinet|trumpet|horn|trombone|harp|"
    r"harpsichord|accordion|saxophone|bassoon|oboe|percussion)\s+"
    r"(?=(?:arrangement|transcription|version)\b)",
    re.I,
)
_TRAILING_BY = re.compile(r"\bby\s+([^;|()\[\]]{2,80})\s*$", re.I)
_TRAILING_DASH_CREDIT = re.compile(r"\s[-\u2013\u2014]\s([^;|()\[\]]{2,80})\s*$")
_TITLE_WORDS = re.compile(
    r"\b(theme|song|waltz|march|dance|jig|reel|air|aria|suite|sonata|concerto|prelude|"
    r"fugue|mass|motet|hymn|carol|variations|excerpt|fantasy|ballad|tune|set|piece|"
    r"overture|symphony|quartet|trio|duet|study|etude|rondo|minuet|gavotte|polka)\b",
    re.I,
)
_PARTICLES = frozenset(
    {"de", "del", "la", "le", "van", "von", "der", "den", "da", "di", "du", "dos", "das", "y", "e"}
)
_ATTRIBUTION_WORD = re.compile(
    r"\b(?:anon\.?|anonymous|anónim[oa]|anonim[oa]|desconocid[oa]|traditional|tradicional|"
    r"trad\.?|popular|volksweise)\b",
    re.I,
)
_LEADING_ID = re.compile(r"^\s*\[[^\]]{1,40}\]\s*")
_PDMX_CODE = re.compile(
    r"\b(?!(?:BWV|KV|Op|Hob|HWV|RV|WWV|Wq|Sz|WoO|Anh|No|Nr|Ps)\b)"
    r"(?:[A-Z][A-Za-z]{1,5}\.\s?\[?\d{1,4}\]?(?:\([ivx]+\))?"
    r"|[A-Z]{2,5}\d{2,4}(?:\([ivx]+\))?"
    r"|[A-Z][A-Za-z]{1,5}\d{1,3}\.\d{2,4})\b(?:\s+[A-Z]\b)?"
)
_OPUS = re.compile(
    r"\bOp(?:us)?\.?\s*\d+[A-Za-z]?(?:\s*(?:No\.?|n[ºo]|nr\.?)\s*\d+)?", re.I
)
_CATALOGUE = re.compile(
    r"\b(?:(?:BWV|KV|Hob|HWV|RV|WWV|Wq|Sz|WoO|Anh)\.?\s*\d+[A-Za-z]?"
    r":?\s*[A-Za-z0-9]*|(?:D|K|L|Z)\.\s?\d+[A-Za-z]?)",
    re.I,
)
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")
_YEAR_RANGE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\s*[-\u2013\u2014]\s*(1[0-9]{3}|20[0-2][0-9])\b")
_LEADING_DASH_CREDIT = re.compile(
    r"^(?P<name>[A-Z][\w'’.\-]*(?:\s+[A-Z][\w'’.\-]*){1,4})\s+[-\u2013\u2014]\s+"
)
_LEADING_COLON_CREDIT = re.compile(r"^(?P<name>[A-Z][^:;|()\[\]]{1,50}?):\s+")
_CREDIT_PARTICLE = re.compile(r"\b(?:de|del|van|von|der|den|da|di|du|le|la)\b", re.I)
_PAREN_CREDIT = re.compile(r"\((?P<text>[A-Z][^()]{3,60})\)")
_TRAILING_SEPARATORS = re.compile(r"^[\s\-–—:;,|.]+|[\s\-–—:;,|.]+$")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,;:.!?])")
_REPEATED_PUNCT = re.compile(r"([:;,])\s*(?:\1\s*)+")
_REPEAT_MARK = re.compile(r"\s+\d+x\b", re.I)
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")
_TOKEN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][\w'’.\-]*", re.UNICODE)


@dataclass(frozen=True)
class ExtractedPerson:
    name: str
    role: str
    position: int
    evidence: str


@dataclass(frozen=True)
class EnsembleCandidate:
    code: str
    description: str
    evidence: str


@dataclass(frozen=True)
class InstrumentCandidate:
    code: str
    label: str
    evidence: str


@dataclass(frozen=True)
class Extraction:
    """Metadatos derivados del texto crudo de una obra."""

    raw: str
    title: str
    subtitle: str | None = None
    key: str | None = None
    attribution: str | None = None
    persons: tuple[ExtractedPerson, ...] = field(default_factory=tuple)
    ensembles: tuple[EnsembleCandidate, ...] = field(default_factory=tuple)
    instruments: tuple[InstrumentCandidate, ...] = field(default_factory=tuple)
    opus: str | None = None
    catalogue: str | None = None
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def composer(self) -> ExtractedPerson | None:
        return next((person for person in self.persons if person.role == "composer"), None)

    @property
    def arrangers(self) -> tuple[ExtractedPerson, ...]:
        return tuple(person for person in self.persons if person.role != "composer")

    def as_dict(self) -> dict[str, Any]:
        """Forma serializable (informes JSONL); sin objetos ni enums."""
        return {
            "raw": self.raw,
            "title": self.title,
            "subtitle": self.subtitle,
            "key": self.key,
            "attribution": self.attribution,
            "persons": [
                {"name": person.name, "role": person.role, "evidence": person.evidence}
                for person in self.persons
            ],
            "ensembles": [
                {"code": item.code, "description": item.description}
                for item in self.ensembles
            ],
            "instruments": [
                {"code": item.code, "label": item.label} for item in self.instruments
            ],
            "opus": self.opus,
            "catalogue": self.catalogue,
            "year": self.year,
            "year_from": self.year_from,
            "year_to": self.year_to,
            "flags": list(self.flags),
        }


def normalize_text(raw: str | None) -> str:
    """HTML decodificado, sin entidades, marcas XML ni espacios invisibles."""
    if not raw:
        return ""
    text = html.unescape(str(raw))
    text = _SYM.sub(" ", text)
    text = _XML.sub(" ", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _INVISIBLE.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def _blank(text: str, start: int, end: int) -> str:
    """Sustituye un tramo por espacios conservando las posiciones del resto."""
    return text[:start] + " " * (end - start) + text[end:]


def _is_credit_name(candidate: str) -> bool:
    """Nombre plausible de crédito (2–5 palabras, sin palabras de título)."""
    text = sanitize_person_name(candidate)[0]
    if not text or _TITLE_WORDS.search(text):
        return False
    tokens = _TOKEN.findall(text)
    if not 2 <= len(tokens) <= 5:
        return False
    lowered = text.lower()
    if lowered in _PARTICLES:
        return False
    for token in tokens:
        if token.lower() in _PARTICLES:
            continue
        if not token[:1].isupper():
            return False
    return True


def _has_credit_marker(candidate: str) -> bool:
    """Señal estructural de nombre: coma, inicial o partícula nobiliaria."""
    return bool(
        "," in candidate
        or re.search(r"\b[A-Z]\.", candidate)
        or _CREDIT_PARTICLE.search(candidate)
    )


def _person_lookup(
    known_person: Callable[[str], bool] | None, candidate: str
) -> bool:
    return bool(known_person and known_person(sanitize_person_name(candidate)[0]))


def _person_from_span(candidate: str, position: int) -> list[ExtractedPerson]:
    parsed = parse_import_name(candidate)
    if parsed.kind != "person":
        return []
    return [
        ExtractedPerson(
            name=person.name, role=person.role_key, position=position, evidence=person.evidence
        )
        for person in parsed.persons
    ]


def _dedupe_people(people: list[ExtractedPerson]) -> tuple[ExtractedPerson, ...]:
    seen: set[tuple[str, str]] = set()
    out: list[ExtractedPerson] = []
    for person in sorted(people, key=lambda item: item.position):
        key = (person.name.casefold(), person.role)
        if key in seen:
            continue
        seen.add(key)
        out.append(person)
    return tuple(out)


def _extract_people(
    text: str, known_person: Callable[[str], bool] | None = None
) -> tuple[list[ExtractedPerson], str, str | None, list[str]]:
    """Personas y atribución; devuelve también el texto enmascarado y las marcas."""
    people: list[ExtractedPerson] = []
    attribution: str | None = None
    flags: list[str] = []
    masked = text

    def take(match: re.Match[str], candidate: str | None = None) -> bool:
        nonlocal masked, attribution
        parsed = parse_import_name(candidate or match.group(0))
        if parsed.kind == "attribution":
            attribution = parsed.attribution_status
        elif parsed.kind != "person":
            return False
        people.extend(
            ExtractedPerson(
                name=person.name,
                role=person.role_key,
                position=match.start(),
                evidence=person.evidence,
            )
            for person in parsed.persons
        )
        masked = _blank(masked, match.start(), match.end())
        return True

    suffix_pattern = re.compile(
        r"(?P<name>[^()\[\];|]{2,60})\s*\(\s*(?:arr|arranger|composer|comp|editor|ed|"
        r"transcriber|transcr|orchestrator|orch)\.?\s*\)",
        re.I,
    )
    for match in suffix_pattern.finditer(masked):
        take(match)
    for match in _ROLE_PHRASE.finditer(masked):
        take(match)
    for match in _SHORT_ROLE_PHRASE.finditer(masked):
        take(match)
    for match in _PAREN_ROLE.finditer(masked):
        take(match)

    for match in _PAREN_CREDIT.finditer(masked):
        content = match.group("text")
        if (
            "," in content
            and _is_credit_name(content)
            and not _TITLE_WORDS.search(content)
        ):
            parsed = parse_import_name(content)
            if parsed.kind == "person":
                people.extend(
                    ExtractedPerson(
                        name=person.name,
                        role="composer",
                        position=match.start(),
                        evidence=f"crédito entre paréntesis: {content[:80]}",
                    )
                    for person in parsed.persons
                )
                masked = _blank(masked, match.start(), match.end())

    leading = _LEADING_DASH_CREDIT.match(masked)
    if (
        leading
        and re.search(r"\b[A-Z]\.", leading.group("name"))
        and _is_credit_name(leading.group("name"))
    ):
        people.extend(_person_from_span(leading.group("name"), 0))
        if people:
            masked = _blank(masked, leading.start(), leading.end())

    leading_colon = _LEADING_COLON_CREDIT.match(masked)
    if leading_colon:
        name = leading_colon.group("name")
        if (
            _is_credit_name(name)
            and (re.search(r"\b[A-Z]\.", name) or _CREDIT_PARTICLE.search(name))
        ):
            people.extend(_person_from_span(name, 0))
            if people:
                masked = _blank(masked, leading_colon.start(), leading_colon.end())

    by_match = _TRAILING_BY.search(masked)
    if by_match:
        candidate = re.split(r"\b(?:for|with)\b", by_match.group(1), maxsplit=1, flags=re.I)[0]
        if _is_credit_name(candidate):
            parsed = parse_import_name(candidate)
            if parsed.kind == "person":
                people.extend(
                    ExtractedPerson(
                        name=person.name,
                        role="composer",
                        position=by_match.start(),
                        evidence=f"crédito tras 'by': {by_match.group(0)[:120]}",
                    )
                    for person in parsed.persons
                )
                masked = _blank(masked, by_match.start(), by_match.end())

    if not people:
        dash_match = _TRAILING_DASH_CREDIT.search(masked)
        if dash_match:
            candidate = dash_match.group(1)
            if known_person is not None:
                accepted = _is_credit_name(candidate) and _person_lookup(known_person, candidate)
            else:
                accepted = _is_credit_name(candidate) and _has_credit_marker(candidate)
            if accepted:
                people.extend(_person_from_span(candidate, dash_match.start()))
                if people:
                    masked = _blank(masked, dash_match.start(), dash_match.end())

    attribution_match = _ATTRIBUTION_WORD.search(masked)
    if attribution_match:
        parsed = parse_import_name(attribution_match.group(0))
        if parsed.kind == "attribution":
            attribution = parsed.attribution_status
            masked = _blank(masked, attribution_match.start(), attribution_match.end())

    return people, masked, attribution, flags


def _extract_ensembles(text: str) -> tuple[EnsembleCandidate, ...]:
    phrases: list[tuple[str, str]] = []
    for match in _PARENTHESES.finditer(text):
        phrases.append((match.group(1), "paréntesis"))
    for match in _FOR_PHRASE.finditer(text):
        phrases.append((match.group(1), "tras 'for'"))
    for token in re.findall(r"\b[A-Z]{2,8}\b", text):
        phrases.append((token, "código en mayúsculas"))

    found: list[EnsembleCandidate] = []
    seen: set[str] = set()
    for phrase, evidence in phrases:
        if len(phrase) > 40 or phrase.casefold().startswith(("the ", "for ", "with ")):
            continue
        info = canonical_ensemble(phrase)
        if info.kind not in {KIND_VOICES, KIND_SPECIAL}:
            continue
        if info.id_canonico in seen:
            continue
        seen.add(info.id_canonico)
        found.append(
            EnsembleCandidate(code=info.id_canonico, description=info.description, evidence=evidence)
        )
    return tuple(found)


def _extract_instruments(
    text: str, vocabulary: InstrumentVocabulary | None
) -> tuple[InstrumentCandidate, ...]:
    if vocabulary is None or not vocabulary:
        return ()
    phrases: list[str] = []
    for match in _FOR_PHRASE.finditer(text):
        phrases.append(match.group(1))
    for match in _PARENTHESES.finditer(text):
        phrases.append(match.group(1))
    for match in _INSTRUMENT_CONTEXT.finditer(text):
        phrases.append(match.group(0))

    found: list[InstrumentCandidate] = []
    seen: set[str] = set()
    for phrase in phrases:
        for candidate in vocabulary.find(phrase):
            if candidate.code in seen:
                continue
            seen.add(candidate.code)
            found.append(
                InstrumentCandidate(
                    code=candidate.code, label=candidate.label, evidence=phrase.strip()
                )
            )
    return tuple(found)


def _blank_descriptors(
    text: str, vocabulary: InstrumentVocabulary | None
) -> str:
    """Retira paréntesis y contextos que solo describen formación o instrumento."""
    masked = text
    for match in reversed(list(_INSTRUMENT_CONTEXT.finditer(text))):
        masked = _blank(masked, match.start(), match.end())
    for match in reversed(list(_PARENTHESES.finditer(text))):
        content = match.group(1)
        if (
            _TITLE_WORDS.search(content)
            or len(content) > 40
            or content.casefold().startswith(("for ", "with "))
        ):
            continue
        info = canonical_ensemble(content)
        descriptor = info.kind in {KIND_VOICES, KIND_SPECIAL}
        if not descriptor and vocabulary is not None:
            descriptor = bool(vocabulary.find(content))
        if descriptor:
            masked = _blank(masked, match.start(), match.end())
    return masked


def _clean_title(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    title = _LEADING_ID.sub("", text)
    stripped = _PDMX_CODE.sub(" ", title)
    if stripped != title:
        flags.append("source_code_removed")
    title = stripped
    repeated = _REPEAT_MARK.sub(" ", title)
    if repeated != title:
        flags.append("repeat_mark_removed")
    title = repeated
    title = _EMPTY_BRACKETS.sub(" ", title)
    title = _SPACE_BEFORE_PUNCT.sub(r"\1", title)
    title = _REPEATED_PUNCT.sub(r"\1", title)
    title = _SPACES.sub(" ", title).strip()
    title = _TRAILING_SEPARATORS.sub("", title).strip()
    return title, flags


def extract_metadata(
    raw: str | None,
    *,
    instrument_vocabulary: InstrumentVocabulary | None = None,
    known_person: Callable[[str], bool] | None = None,
) -> Extraction:
    """Extrae metadatos deterministas del texto crudo de una obra.

    `known_person` permite validar créditos ambiguos ("Título - Nombre") contra el
    catálogo de personas. Sin él, esos créditos solo se aceptan con una señal
    estructural (coma, inicial o partícula); los roles explícitos ("arr. X") no
    dependen del catálogo.
    """
    text = normalize_text(raw)
    if not text:
        return Extraction(raw=raw or "", title="", flags=("empty_text",))

    flags: list[str] = []
    tonalities: list[TonalitySpan] = find_tonalities(text)
    working = text
    for span in reversed(tonalities):
        working = _blank(working, span.start, span.end)

    working = _blank_descriptors(working, instrument_vocabulary)
    people, working, attribution, people_flags = _extract_people(working, known_person)
    flags.extend(people_flags)

    title, title_flags = _clean_title(working)
    flags.extend(title_flags)
    if not title:
        title = _TRAILING_SEPARATORS.sub("", _SPACES.sub(" ", text)).strip()
        flags.append("title_fallback_raw")
    if title.isupper() and len(title) > 3:
        flags.append("title_uppercase")
    if people and attribution:
        flags.append("mixed_credit_and_attribution")

    subtitle = None
    for separator in (" \u2013 ", " \u2014 "):
        if separator in title:
            head, tail = title.split(separator, 1)
            if head.strip() and tail.strip():
                subtitle = tail.strip()
                title = head.strip()
                flags.append("subtitle_split")
                break

    years = [int(value) for value in _YEAR.findall(" ".join(_PARENTHESES.findall(text)))]
    year_range = _YEAR_RANGE.search(" ".join(_PARENTHESES.findall(text)))
    year_from = year_to = None
    if year_range:
        year_from, year_to = int(year_range.group(1)), int(year_range.group(2))
        flags.append("year_range")
    year = years[0] if years and not year_range else None

    catalogue_match = _CATALOGUE.search(text)
    opus_match = _OPUS.search(text)
    if catalogue_match:
        flags.append("catalogue_found")
    if opus_match:
        flags.append("opus_found")

    return Extraction(
        raw=raw or "",
        title=title,
        subtitle=subtitle,
        key=join_tonalities(tonalities),
        attribution=attribution,
        persons=_dedupe_people(people),
        ensembles=_extract_ensembles(text),
        instruments=_extract_instruments(text, instrument_vocabulary),
        opus=opus_match.group(0).strip() if opus_match else None,
        catalogue=catalogue_match.group(0).strip() if catalogue_match else None,
        year=year,
        year_from=year_from,
        year_to=year_to,
        flags=tuple(dict.fromkeys(flags)),
    )
