"""Función canónica de formaciones vocales (`ensembles`) — fuente única.

Convierte cualquier texto (nombre o código de ensemble, o la consulta del buscador) en un
`CanonicalEnsemble`: un `id_canonico` unívoco + la descomposición en voces, la familia y una
descripción reconstruible. Ver `docs/osap/ensemble-canonical-model.md`.

Reglas (basadas en `osap_normalize`, ampliadas):
- Alfabeto y orden canónico: S, MZ, A, CT, T, BAR, B.
- Un id se compone con una aparición por voz efectiva: `SSAATTBB`, `TTBARB`.
- Bloques independientes (multi-coro, separados por `.`) se unen con `_`: `SATB_SATB`.
- Modificadores de ejecución (SOLO, DIVISI, A CAPPELLA…) no crean voz; solo el infijo
  `_SOLO_` cuando hay una voz de solista identificable.
- Casos especiales: `UNISON[_FEMALE|_MALE|_MIXED]`, `CHILDREN`, `TREBLE`, `DESCANT`,
  `INSTRUMENTAL_<sfx>` y roles (`CANTOR`, `CONGREGATION`, …).
- Una **letra suelta** solo es voz con evidencia contextual (otra voz, un calificador tipo
  SOLO/VERSE, un conector, o que el resto del texto sea funcional). Así `A GLÄUBIGE SEELE`,
  `T EVANGELISTA` o `B JESUS` no se leen como formaciones.
- Sin voz identificable: `INVALID_OR_INSTRUMENTAL` (notación instrumental), `UNKNOWN`
  (material vocal **no interpretable**, p. ej. BAR/BARB pegados) o `UNSPECIFIED`
  (el texto **no da** formación concreta: `MIXED`, `DIV`, `VOICE`, `PARTSONG`…).

Determinista e idempotente: `canonical_ensemble(x).id_canonico` es estable.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

# ── Voces ────────────────────────────────────────────────────────────────────

VOICE_ORDER: tuple[str, ...] = ("S", "MZ", "A", "CT", "T", "BAR", "B")

VOICE_DISPLAY: Mapping[str, str] = {
    "S": "Soprano",
    "MZ": "Mezzo",
    "A": "Alto",
    "CT": "Contratenor",
    "T": "Tenor",
    "BAR": "Barítono",
    "B": "Bajo",
}

VOICE_WORDS: Mapping[str, str] = {
    "SOPRANO": "S", "SOPRANOS": "S", "SOP": "S", "SOPRANI": "S",
    "MEZZO": "MZ", "MEZZOSOPRANO": "MZ", "MEZZOSOPRANOS": "MZ",
    "MEDIUS": "MZ", "MED": "MZ", "M": "MZ",
    "ALTO": "A", "ALTOS": "A", "ALTI": "A",
    "COUNTERTENOR": "CT", "CONTRALTO": "CT", "CONTRA": "CT", "C": "CT",
    "TENOR": "T", "TENORS": "T", "TENORE": "T", "TENORI": "T",
    "BARITONE": "BAR", "BARITONO": "BAR", "BARYTON": "BAR", "BARITONES": "BAR",
    "BASS": "B", "BASSES": "B", "BASSO": "B", "BASSI": "B",
    "HIGH": "S", "LOW": "B", "MEDIUM": "A",
}

VOICE_ABBR: Mapping[str, str] = {
    "BARB": "BAR", "BAR": "BAR", "BRB": "BAR", "BR": "BAR",
    "MEZ": "MZ", "MZ": "MZ", "MS": "MZ", "SMEZ": "MZ", "SMZ": "MZ", "MED": "MZ", "M": "MZ",
    "CT": "CT",
}

# Tokens ignorados (modificadores, conectores, decoración).
STOPWORDS: frozenset[str] = frozenset({
    "CHOIR", "CHOIRS", "CHORUS", "CHORAL", "ENSEMBLE", "GROUP",
    "VERSE", "VERSES", "MOVEMENT", "SECTION",
    "DIV", "DIVISI", "DIVSI", "DIVISIONS", "DIVISION",
    "CAPPELLA", "A_CAPP", "ACAPP", "ACAPPELLA",
    "OPTIONAL", "OPT", "WITH", "AND", "OR", "PLUS", "ONLY",
    "FOR", "IN", "OF", "THE", "TO", "AS", "BY",
    "VOICE", "VOICES", "PART", "PARTS", "PARTSONG", "PARTSONGS",
    "EQUAL", "RIPIENO", "RIPIENI", "SEMI", "SEMICHORUS",
    "QUARTET", "DUET", "DUETS", "TRIO", "TRIOS", "SOLOS", "SOLOSVV",
    "TIMES", "XX", "X", "ND", "RD", "TH",
})

# ── Roles y casos especiales ─────────────────────────────────────────────────

SPECIAL_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CANTOR_CONGREGATION", ("CANTOR & CONGREGATION",)),
    ("CANTOR", ("CANTOR",)),
    ("CONGREGATION", ("CONGREGATION",)),
    ("NARRATOR", ("NARRATOR",)),
    ("SPEAKER", ("SPEAKER", "RECITANTE")),
    ("CELEBRANT", ("CELEBRANT",)),
    ("EQUAL_VOICES", ("EQUAL VOICES", "TWO EQUAL VOICES")),
    ("FEMALE_CHOIR", ("WOMEN", "WOMENS", "FEMALE CHOIR", "FEMALE VOICES")),
    ("MALE_CHOIR", ("MEN", "MENS", "MALE CHOIR", "MALE VOICES")),
)

UNISON_KEYWORDS: frozenset[str] = frozenset({"UNISON", "UNISONO"})
UNISON_MODIFIERS: tuple[tuple[str, str], ...] = (
    ("FEMALE", "UNISON_FEMALE"),
    ("MALE", "UNISON_MALE"),
    ("MEN", "UNISON_MALE"),
    ("MIXED", "UNISON_MIXED"),
)
CHILDREN_KEYWORDS: frozenset[str] = frozenset({"CHILD", "CHILDREN", "CHILDRENS"})
TREBLE_KEYWORDS: frozenset[str] = frozenset({"TREBLE", "TREBLES"})
DESCANT_KEYWORDS: frozenset[str] = frozenset({"DESCANT", "DESCANTS"})

INSTRUMENT_SUFFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BC", ("BC",)),
    ("ORG", ("ORG", "ORGAN")),
    ("PF", ("PF", "PIANO")),
    ("ORCH", ("ORCH", "ORCHESTRA")),
    ("BRASS", ("BRASS",)),
    ("TROMBON", ("TROMBON", "TROMBONE")),
    ("PERC", ("PERCUSSION",)),
    ("STRINGS", ("STRINGS",)),
    ("WWMM", ("WWMM",)),
    ("INSTR", ("INSTR",)),
)
ALL_INSTRUMENT_TOKENS: frozenset[str] = frozenset(
    kw for _, kws in INSTRUMENT_SUFFIXES for kw in kws
)

SOLO_KEYWORDS: frozenset[str] = frozenset({"SOLO", "SOLI", "SOLOIST", "SOLOISTS", "SOLISTA"})

# Contexto para aceptar una letra suelta como voz (regla de evidencia).
CONTEXT_QUALIFIERS: frozenset[str] = SOLO_KEYWORDS | frozenset({
    "VERSE", "VERSES", "CHOIR", "CHOIRS", "CHORUS", "CHORAL",
    "DIV", "DIVISI", "DIVSI", "RIPIENO", "RIPIENI", "PART", "PARTS",
})
CONNECTOR_WORDS: frozenset[str] = frozenset({"AND", "OR", "Y", "E"})
SUPPRESSORS: frozenset[str] = frozenset({
    "OF", "EACH", "EVERY", "ONE", "TWO", "THREE", "SOME",
    "LOWEST", "HIGHEST", "ONLY", "PART",
})
FUNCTION_WORDS: frozenset[str] = frozenset({
    "AND", "OR", "WITH", "IN", "OF", "FOR", "THE", "TO", "IS", "ARE", "WAS",
    "PLUS", "ALSO", "NOT", "UNLESS", "OTHERWISE", "AS", "IF", "THEN", "ONLY",
    "BOTH", "SAME", "SUCH", "THAN", "THAT", "THIS", "THESE", "THOSE",
})
# Letras que aparecen en notación de voces (para detectar material vocal no interpretable).
_VOICE_LETTERS: frozenset[str] = frozenset("SATBCMZR")

INVALID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b[A-G]-[A-G]'?\b"),      # C-A', D-D', E-G'
    re.compile(r"^[A-G]\d?$"),              # F3, F4, C2, C3
    re.compile(r"^-\s?\d+$"),               # – 5, – 8 (normalizados a -)
    re.compile(r"TRANSPOSITION"),
    re.compile(r"SEE EDITION"),
    re.compile(r"AD LIBITUM"),
    re.compile(r"^BC$"),
    re.compile(r"^NONE$"),
    re.compile(r"^VARIOUS$"),
)
INVALID_EXCEPTIONS: frozenset[str] = frozenset({"S", "A", "T", "B"})

SEGMENT_SEPARATORS = re.compile(r"[.]+|\s*[×]\s*|\s*/\s*|\s*\|\s*")
LEX_SEPARATORS = re.compile(r"[,;:/+×]|(\s-\s)|(\u2013)|(\u2014)")
TOKEN_RE = re.compile(r"[A-Z]+")

CANONICAL_UNKNOWN = "UNKNOWN"
CANONICAL_INVALID = "INVALID_OR_INSTRUMENTAL"
CANONICAL_SOLI_GROUP = "SOLI_GROUP"
CANONICAL_CHILDREN = "CHILDREN"
CANONICAL_TREBLE = "TREBLE"
CANONICAL_DESCANT = "DESCANT"
CANONICAL_UNISON = "UNISON"
CANONICAL_INSTRUMENTAL = "INSTRUMENTAL"
CANONICAL_SOLO_INFIX = "SOLO"
# Texto sin formación concreta (descriptor): `MIXED`, `DIV`, `VOICE`, `PARTSONG`…
CANONICAL_DESCRIPTOR = "UNSPECIFIED"

KIND_VOICES = "VOICES"
KIND_SPECIAL = "SPECIAL"
KIND_INVALID = "INVALID"
KIND_DESCRIPTOR = "DESCRIPTOR"
KIND_UNKNOWN = "UNKNOWN"

# Ids centinela: la función debe reconocer su propia salida (idempotencia).
_SENTINELS: dict[str, str] = {
    CANONICAL_UNKNOWN: KIND_UNKNOWN,
    CANONICAL_INVALID: KIND_INVALID,
    CANONICAL_DESCRIPTOR: KIND_DESCRIPTOR,
}


@dataclass(frozen=True)
class CanonicalEnsemble:
    id_canonico: str
    segments: tuple[str, ...]
    voice_counts: Mapping[str, int]
    total_voices: int
    family: str
    kind: str
    description: str
    notes: tuple[str, ...]


# ── Normalización léxica ─────────────────────────────────────────────────────

def lex_normalize(code: str | None) -> str:
    if code is None:
        return ""
    s = str(code).upper().strip()
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"[()\[\]'\"]", " ", s)
    s = re.sub(r"\bA[_\s]?CAPP\w*\b", " CAPPELLA ", s)
    s = LEX_SEPARATORS.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _split_segments(norm_code: str) -> list[str]:
    return [s for s in SEGMENT_SEPARATORS.split(norm_code) if s.strip()]


def _tokenize(norm_code: str) -> list[str]:
    return TOKEN_RE.findall(norm_code)


# ── Extracción de voces ──────────────────────────────────────────────────────

def _expand_sigla(tok: str) -> Counter | None:
    i, n = 0, len(tok)
    result: Counter = Counter()
    while i < n:
        matched = False
        for key in sorted(VOICE_ABBR, key=len, reverse=True):
            if tok.startswith(key, i):
                result[VOICE_ABBR[key]] += 1
                i += len(key)
                matched = True
                break
        if matched:
            continue
        ch = tok[i]
        if ch in VOICE_ORDER:
            result[ch] += 1
            i += 1
            continue
        return None
    return result if result else None


def _extract_voices(norm_code: str) -> Counter:
    """Extracción permisiva (acepta letras sueltas). Para vecinos de SOLO."""
    voices: Counter = Counter()
    for tok in _tokenize(norm_code):
        if tok in ALL_INSTRUMENT_TOKENS:
            continue
        if tok in VOICE_WORDS:
            voices[VOICE_WORDS[tok]] += 1
        elif tok in VOICE_ABBR:
            voices[VOICE_ABBR[tok]] += 1
        elif tok in STOPWORDS:
            continue
        else:
            expanded = _expand_sigla(tok)
            if expanded:
                voices.update(expanded)
    return voices


def _others_functional(tokens: list[str], lone_indexes: set[int]) -> bool:
    """True si todo token no-voz es funcional/modificador (letras sueltas aparte)."""
    for i, tok in enumerate(tokens):
        if i in lone_indexes:
            continue
        if tok in STOPWORDS or tok in SOLO_KEYWORDS or tok in FUNCTION_WORDS:
            continue
        if tok in ALL_INSTRUMENT_TOKENS or tok in VOICE_WORDS or tok in VOICE_ABBR:
            continue
        if len(tok) > 1 and _expand_sigla(tok) is not None:
            continue
        return False
    return True


def _looks_like_voice_material(tokens: list[str]) -> bool:
    """True si hay material que parece notación vocal pero no se pudo interpretar.

    Distingue `UNKNOWN` (formación ininterpretable) de `DESCRIPTOR` (texto sin formación).
    """
    for tok in tokens:
        if tok in STOPWORDS or tok in ALL_INSTRUMENT_TOKENS:
            continue
        if tok in VOICE_WORDS or tok in VOICE_ABBR:
            continue
        if "BAR" in tok or "BRB" in tok:
            return True
        if len(tok) >= 2 and all(ch in _VOICE_LETTERS for ch in tok):
            return True
    return False


def _extract_voices_ctx(tokens: list[str], norm_code: str) -> Counter:
    """Extrae voces aplicando la regla de contexto de letras sueltas."""
    voices: Counter = Counter()
    lone: list[tuple[int, str]] = []
    for i, tok in enumerate(tokens):
        if tok in ALL_INSTRUMENT_TOKENS or tok in STOPWORDS:
            continue
        if tok in VOICE_WORDS:
            voices[VOICE_WORDS[tok]] += 1
        elif tok in VOICE_ABBR:
            voices[VOICE_ABBR[tok]] += 1
        elif len(tok) == 1 and tok in VOICE_ORDER:
            lone.append((i, tok))
        elif len(tok) > 1:
            expanded = _expand_sigla(tok)
            if expanded is not None:
                voices.update(expanded)

    has_other_voice = bool(voices)
    has_qualifier = any(t in CONTEXT_QUALIFIERS for t in tokens)
    has_connector = any(t in CONNECTOR_WORDS for t in tokens) or "&" in norm_code
    others_functional = _others_functional(tokens, {i for i, _ in lone})
    for i, letter in lone:
        previous = tokens[i - 1] if i > 0 else None
        right = tokens[i + 1] if i + 1 < len(tokens) else None
        if previous in SUPPRESSORS:
            continue
        connected = has_connector or previous in CONNECTOR_WORDS or right in CONNECTOR_WORDS
        if has_other_voice or has_qualifier or connected or others_functional:
            voices[letter] += 1
    return voices


def build_signature(voices: Mapping[str, int]) -> str:
    return "".join(v * voices[v] for v in VOICE_ORDER if voices.get(v, 0) > 0)


def _extract_solo_voices(norm_code: str) -> Counter:
    tokens = _tokenize(norm_code)
    result: Counter = Counter()
    for i, tok in enumerate(tokens):
        if tok in SOLO_KEYWORDS:
            for j in (i - 1, i + 1):
                if 0 <= j < len(tokens):
                    v = _extract_voices(tokens[j])
                    if sum(v.values()) == 1:
                        result.update(v)
    return result


# ── Detección de rasgos ──────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[_&\s]+", " ", text).strip()


def _detect_special_role(norm_code: str) -> str | None:
    tokens = set(_tokenize(norm_code))
    slug = _slug(norm_code)
    for canonical, keywords in SPECIAL_ROLES:
        for kw in keywords:
            if re.search(rf"\b{re.escape(_slug(kw))}\b", slug):
                return canonical
            if " " not in kw and "&" not in kw and kw in tokens:
                return canonical
    return None


def _detect_unison(norm_code: str) -> str | None:
    if not any(k in norm_code for k in UNISON_KEYWORDS):
        return None
    for mod, canonical in UNISON_MODIFIERS:
        if mod in norm_code:
            return canonical
    return CANONICAL_UNISON


def _detect_instrument(norm_code: str) -> str | None:
    tokens = set(_tokenize(norm_code))
    for suffix, keywords in INSTRUMENT_SUFFIXES:
        if tokens & set(keywords):
            return suffix
    return None


def _is_invalid(norm_code: str) -> bool:
    if norm_code in INVALID_EXCEPTIONS:
        return False
    return any(pat.search(norm_code) for pat in INVALID_PATTERNS)


# ── Clasificación de un bloque ───────────────────────────────────────────────

def _classify_segment(norm_code: str, notes: list[str]) -> str:
    if not norm_code:
        notes.append("bloque vacío")
        return CANONICAL_DESCRIPTOR
    if norm_code in _SENTINELS:
        notes.append("centinela")
        return norm_code
    if _is_invalid(norm_code):
        notes.append("patrón no vocal")
        return CANONICAL_INVALID

    tokens = _tokenize(norm_code)
    instr = _detect_instrument(norm_code)
    voices = _extract_voices_ctx(tokens, norm_code)
    sig = build_signature(voices)

    if instr and not sig:
        notes.append(f"instrumental puro ({instr})")
        return f"{CANONICAL_INSTRUMENTAL}_{instr}"

    unison = _detect_unison(norm_code)
    if unison:
        notes.append("unísono")
        return f"{unison}_{instr}" if instr else unison

    if any(k in norm_code for k in CHILDREN_KEYWORDS):
        notes.append("coro infantil")
        return CANONICAL_CHILDREN
    if any(k in norm_code for k in TREBLE_KEYWORDS):
        notes.append("voces blancas")
        return CANONICAL_TREBLE
    if any(k in norm_code for k in DESCANT_KEYWORDS):
        notes.append("descant")
        return CANONICAL_DESCANT

    role = _detect_special_role(norm_code)
    if role:
        notes.append(f"rol {role}")
        return f"{role}_{instr}" if instr else role

    has_solo = bool(set(tokens) & SOLO_KEYWORDS)
    if has_solo:
        solo_voices = _extract_solo_voices(norm_code)
        solo_sig = build_signature(solo_voices)
        if sig and solo_sig:
            if Counter(voices) == Counter(solo_voices):
                notes.append("solo puro")
                return f"{CANONICAL_SOLO_INFIX}_{solo_sig}"
            coro = Counter(voices)
            for v, n in solo_voices.items():
                coro[v] = max(0, coro.get(v, 0) - n)
            coro_sig = build_signature(coro) or sig
            notes.append("coro + solista con voz")
            return f"{coro_sig}_{CANONICAL_SOLO_INFIX}_{solo_sig}"
        if sig:
            notes.append("coro con solistas sin voz")
            return f"{sig}_{CANONICAL_SOLO_INFIX}"
        notes.append("grupo solista genérico")
        return CANONICAL_SOLI_GROUP

    if sig:
        notes.append("coro con firma vocal")
        return f"{sig}_{instr}" if instr else sig

    if _looks_like_voice_material(tokens):
        notes.append("material vocal no interpretable")
        return CANONICAL_UNKNOWN
    notes.append("texto sin formación concreta")
    return CANONICAL_DESCRIPTOR


# ── Descripción y familia ────────────────────────────────────────────────────

def _family(voices: Mapping[str, int]) -> str:
    fem = sum(voices.get(v, 0) for v in ("S", "MZ", "A"))
    male = sum(voices.get(v, 0) for v in ("CT", "T", "BAR", "B"))
    if fem and male:
        return "MIXED"
    if fem:
        return "FEMALE"
    if male:
        return "MALE"
    return "UNKNOWN"


def _describe(kind: str, id_canonico: str, voices: Mapping[str, int]) -> str:
    if kind == KIND_INVALID:
        return "No vocal o instrumental (sin formación reconocible)"
    if kind == KIND_UNKNOWN:
        return "Formación no reconocida"
    if kind == KIND_DESCRIPTOR:
        return "Sin formación concreta (texto descriptivo)"
    if id_canonico.startswith(CANONICAL_UNISON):
        mod = id_canonico[len(CANONICAL_UNISON):].strip("_").lower()
        return f"Unísono{(' ' + mod) if mod else ''}"
    if id_canonico == CANONICAL_CHILDREN:
        return "Coro infantil"
    if id_canonico == CANONICAL_TREBLE:
        return "Voces blancas (treble)"
    if id_canonico == CANONICAL_DESCANT:
        return "Descant (voz aguda solista)"
    if id_canonico == CANONICAL_SOLI_GROUP:
        return "Grupo solista"
    parts = [
        f"{VOICE_DISPLAY[v]}{('×' + str(voices[v])) if voices.get(v, 0) > 1 else ''}"
        for v in VOICE_ORDER
        if voices.get(v, 0) > 0
    ]
    if not parts:
        return id_canonico
    fam = _family(voices)
    fam_txt = {"MIXED": "mixto", "FEMALE": "femenino", "MALE": "masculino"}.get(fam, "")
    total = sum(voices.values())
    head = f"Conjunto {fam_txt} a {total} voces".strip()
    return f"{head}: {', '.join(parts)}"


# ── API pública ──────────────────────────────────────────────────────────────

def canonical_ensemble(text: str | None) -> CanonicalEnsemble:
    """Canonicaliza un texto de formación vocal. Ver contrato en el módulo."""
    norm = lex_normalize(text)
    if not norm:
        return CanonicalEnsemble(
            id_canonico=CANONICAL_DESCRIPTOR,
            segments=(),
            voice_counts={},
            total_voices=0,
            family="UNKNOWN",
            kind=KIND_DESCRIPTOR,
            description="Sin formación concreta (texto vacío)",
            notes=("cadena vacía",),
        )

    if norm in _SENTINELS:
        kind = _SENTINELS[norm]
        return CanonicalEnsemble(
            id_canonico=norm,
            segments=(norm,),
            voice_counts={},
            total_voices=0,
            family="UNKNOWN",
            kind=kind,
            description=_describe(kind, norm, {}),
            notes=("centinela",),
        )

    segments = _split_segments(norm)
    # `S.A.T.B.` (letras sueltas separadas por punto) es una sola formación; `SATB.SATB`
    # (bloques multi-letra) es multi-coro.
    if len(segments) > 1 and all(len(s) == 1 and s in VOICE_ORDER for s in segments):
        segment_texts = ["".join(segments)]
    elif len(segments) <= 1:
        segment_texts = [norm]
    else:
        segment_texts = segments

    notes: list[str] = []
    ids = [_classify_segment(seg, notes) for seg in segment_texts]
    # `|` separa bloques (multi-coro). No se usa `_` porque ya es el infijo `_SOLO_` y los
    # ids especiales (`UNISON_FEMALE`): el id debe poder re-canonicalizarse (idempotencia).
    id_canonico = "|".join(ids)

    voices = _extract_voices(norm)
    kind = KIND_VOICES
    if len(ids) == 1:
        if ids[0] in (CANONICAL_INVALID,):
            kind = KIND_INVALID
        elif ids[0] == CANONICAL_UNKNOWN:
            kind = KIND_UNKNOWN
        elif ids[0] == CANONICAL_DESCRIPTOR:
            kind = KIND_DESCRIPTOR
        elif ids[0].startswith((CANONICAL_UNISON, CANONICAL_CHILDREN, CANONICAL_TREBLE,
                                CANONICAL_DESCANT, CANONICAL_INSTRUMENTAL, "CANTOR",
                                "CONGREGATION", "NARRATOR", "SPEAKER", "CELEBRANT",
                                "EQUAL_VOICES", "FEMALE_CHOIR", "MALE_CHOIR",
                                CANONICAL_SOLI_GROUP)):
            kind = KIND_SPECIAL

    # Multi-bloque sin voces: hereda el centinela de sus segmentos (no es VOICES).
    if kind == KIND_VOICES and sum(voices.values()) == 0:
        special_prefix = (CANONICAL_UNISON, CANONICAL_CHILDREN, CANONICAL_TREBLE,
                          CANONICAL_DESCANT, CANONICAL_INSTRUMENTAL, "CANTOR",
                          "CONGREGATION", "NARRATOR", "SPEAKER", "CELEBRANT",
                          "EQUAL_VOICES", "FEMALE_CHOIR", "MALE_CHOIR", CANONICAL_SOLI_GROUP)
        if any(i.startswith(special_prefix) for i in ids):
            kind = KIND_SPECIAL
        elif any(i == CANONICAL_UNKNOWN for i in ids):
            kind = KIND_UNKNOWN
        elif any(i == CANONICAL_INVALID for i in ids):
            kind = KIND_INVALID
        elif any(i == CANONICAL_DESCRIPTOR for i in ids):
            kind = KIND_DESCRIPTOR

    return CanonicalEnsemble(
        id_canonico=id_canonico,
        segments=tuple(ids),
        voice_counts=dict(voices),
        total_voices=sum(voices.values()),
        family=_family(voices),
        kind=kind,
        description=_describe(kind, id_canonico, voices),
        notes=tuple(notes),
    )


def canonical_id(text: str | None) -> str:
    """Atajo: sólo el `id_canonico`."""
    return canonical_ensemble(text).id_canonico
