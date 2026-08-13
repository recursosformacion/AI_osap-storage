from __future__ import annotations

import re

REVIEW_CORRECT = "correct"          # correcto (revisado y válido)
REVIEW_INCORRECT = "incorrect"      # incorrecto / sospechoso (va a la lista de revisión manual)
REVIEW_REVIEWED = "reviewed"        # revisado sin veredicto definitivo
REVIEW_NOT_REVIEWED = "not_reviewed"  # no revisado todavía

# Solo letras, espacios, guiones, puntos y comas (nombre de persona razonable).
_SIMPLE_NAME = re.compile(r"^[A-Za-zÀ-ÿ'.\-, ]+$")
_HAS_LETTER = re.compile(r"[A-Za-zÀ-ÿ]")
# Patrones típicos de no-compositor en el campo de autor de partituras.
_NOISE_PATTERNS = (
    "arranged from",
    "arranged by",
    "arranged",
    "attributed to",
    "attrib.",
    "attr.",
    "arr.",
    "arr ",
    " by ",
    "by ",
    "written by",
    "music by",
    "original music",
    "tune is",
    " page ",
    "tome",
    "feat",
    "solo ",
    "&",
    "/",
)
_NOISE_CHARS = set("[")
# Palabras únicas que nunca son un compositor (para el último recurso de extracción).
_NOISE_SINGLE = {
    "by", "arr", "arranged", "the", "and", "or", "for", "a", "an", "of", "in", "on",
    "to", "from", "page", "tome", "solo", "duet", "song", "tune", "melody", "music",
    "verse", "chorus", "traditional", "anon", "anonymous", "unknown", "na",
}

# Marcadores de mojibake (bytes UTF-8 de cirílico/japonés mal decodificados como Latin-1).
# Ð (U+00D0) y Ã (U+00C3) son leading-bytes de UTF-8; casi nunca aparecen en nombres reales.
_MOJIBAKE_HARD = "\u00d0\u00c3"  # Ð Ã
_MOJIBAKE_MARKERS = "\u00d0\u00c3\u00c5\u00e3\u00e5\u00e7\u00ea\u00eb\u00ee\u00ed\u00ec"  # Ð Ã Å ã å ç ê ë î í ì


def is_mojibake(name: str | None) -> bool:
    """True si el nombre parece texto corrupto por una conversión UTF-8 <-> Latin-1.

    Detecta la firma clásica de mojibake: caracter de reemplazo (U+FFFD), presencia de
    Ð/Ã (leading-bytes de UTF-8), o >=2 marcadores. Permite distinguir nombres no latinos
    corruptos de nombres cirílicos/chinos/japoneses válidos.
    """
    s = name or ""
    if "\ufffd" in s:
        return True
    if any(ch in _MOJIBAKE_HARD for ch in s):
        return True
    return sum(1 for ch in s if ch in _MOJIBAKE_MARKERS) >= 2


# Partículas de nombre que se conservan en minúscula (no se tratan como tokens de apellido).
PARTICULAS_VALIDAS = {"de", "del", "van", "von", "di", "da", "y", "la", "le", "dos", "den"}


def clean_composer_name(name: str | None) -> str:
    """Limpia un nombre de compositor antes de almacenarlo.

    Solo conserva letras (incluidas tildes), guiones y espacios. Todo lo demás
    (comillas y apóstrofes rectos o curvos, puntuación, cifras, símbolos, llaves,
    corchetes...) se reemplaza por un espacio. Después:
    - quita los guiones iniciales y finales (un nombre no empieza ni acaba en "-");
    - normaliza los espacios.

    No modifica mayúsculas/minúsculas; es una limpieza de caracteres, no de identidad.
    """
    s = (name or "").strip()
    s = s.replace("…", " ").replace("...", " ")
    out: list[str] = []
    for ch in s:
        if ch.isalpha():  # letras con/sin tilde (incluye otros alfabetos)
            out.append(ch)
        elif ch in "-–—":
            out.append("-")
        elif ch.isspace():
            out.append(" ")
        else:
            out.append(" ")  # comillas, apóstrofes, puntuación, cifras, símbolos -> espacio
    cleaned = "".join(out)
    cleaned = cleaned.strip(" -")
    return " ".join(cleaned.split())


def is_suspicious(name: str | None) -> bool:
    """True si el nombre probablemente no es un compositor limpio."""
    return classify_composer_name(name) != REVIEW_CORRECT


# Palabras que descartan un nombre como compositor (contexto no-antroponímico).
PALABRAS_PROHIBIDAS = {
    "song", "music", "track", "album", "obras", "works", "version", "traditional",
    "anonymous", "anonimo", "pop", "rock", "jazz", "bluegrass", "symphony", "concerto",
    "sonata", "part", "vol", "op", "arr", "arranged", "tune", "melody", "chorus", "verse",
    "page", "tome", "solo", "duet", "book", "movement", "piece",
}
# Partículas de nombre que se conservan (van, von, de...).
PARTICULAS = {"de", "del", "van", "von", "di", "da", "der", "den", "la", "le", "y", "st"}


def validar_nombre_compositor(nombre: str | None) -> tuple[bool, float, str]:
    """Valida que un nombre (candidato ya extraído) parezca un compositor.

    Devuelve (válido, puntuación, diagnóstico). Es un validador de la forma del nombre,
    no un extractor: debe aplicarse al candidato extraído, no al texto bruto con ruido.
    """
    texto = (nombre or "").strip()
    if not texto:
        return False, 0.0, "Vacío"
    texto = re.sub(r"([a-z])([A-Z])", r"\1 \2", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    tokens = [t for t in texto.split() if t]
    if not tokens:
        return False, 0.0, "Vacío"

    # Palabra única (apellido/autor único, p. ej. "Chopin").
    if len(tokens) == 1:
        token = tokens[0]
        if len(token) <= 1 or token.isdigit():
            return False, 0.0, "Inicial o número aislado"
        if token.istitle() and token.lower() not in PALABRAS_PROHIBIDAS:
            return True, 0.7, "Apellido único"
        return False, 0.0, "Palabra única no válida"

    puntuacion = 0.0
    capitalizadas = 0
    for token in tokens:
        tl = token.lower()
        if tl in PALABRAS_PROHIBIDAS:
            return False, 0.0, f"Palabra prohibida: {token}"
        if len(token) == 1 and token.isupper():
            puntuacion += 1.0
            capitalizadas += 1
        elif token.istitle():
            puntuacion += 1.5
            capitalizadas += 1
        elif token.isupper() and len(token) > 1:
            puntuacion += 1.2
            capitalizadas += 1
        elif tl in PARTICULAS:
            puntuacion += 0.8

    if len(tokens) == 2 and capitalizadas >= 1 and puntuacion >= 2.0:
        return True, puntuacion, "Estructura de 2 palabras (Inicial + Apellido)"
    if puntuacion >= 2.5:
        return True, puntuacion, "Alta probabilidad antroponímica"
    return False, puntuacion, "Puntuación insuficiente"


# Marcas tras las que suele venir el nombre del compositor.
_AFTER_MARKERS = ("attributed to ", "attrib. ", "attr. ", "arranged by ", "arranged from ")
_BY_RE = re.compile(r"\bby\b", re.IGNORECASE)

# Modelo spaCy para NER (opcional). Se carga perezosamente; si no está disponible,
# se usa solo la heurística.
_SPACY_MODEL = "en_core_web_md"
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy  # type: ignore

            _nlp = spacy.load(_SPACY_MODEL)
        except Exception:
            _nlp = False
    return _nlp or None


def _ner_candidate(text: str) -> str | None:
    nlp = _get_nlp()
    if nlp is None:
        return None
    doc = nlp(text)
    persons = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
    if not persons:
        return None
    # Preferir la persona más larga (suele ser el nombre completo del compositor).
    return max(persons, key=len).strip()


def _heuristic_candidate(s: str) -> str | None:
    lower = s.lower()
    cand: str | None = None
    for marker in _AFTER_MARKERS:
        idx = lower.find(marker)
        if idx != -1:
            cand = s[idx + len(marker):]
            break
    if cand is None:
        m = re.search(r"\barr(?:\.|anged)", lower)
        if m:
            cand = s[: m.start()]
    if cand is None:
        matches = list(_BY_RE.finditer(lower))
        if matches:
            last = matches[-1]
            cand = s[last.end():]
    if not cand:
        return None
    return cand.strip(" []()\t.:")


def extract_composer_name(name: str | None) -> str | None:
    """Intenta recuperar un nombre de compositor plausible dentro de un campo ruidoso.

    Estrategia (determinista):
    1. Heurística por marcas (arranged by/from, attributed to, arr., " by ").
    2. Si no, NER (spaCy en_core_web_md): extrae la entidad PERSON más larga.
    3. Como último recurso, el texto limpio completo.
    El candidato resultante pasa por `validar_nombre_compositor` (puntuación antroponímica);
    si no es válido, se devuelve None.
    """
    s = (name or "").strip()
    if not s:
        return None

    if is_mojibake(s):
        return None

    cand = _heuristic_candidate(s)
    if cand is None:
        cand = _ner_candidate(s)

    candidates: list[str] = []
    if cand:
        candidates.append(clean_composer_name(cand))
    candidates.append(clean_composer_name(s))  # último recurso: el texto limpio completo

    for c in candidates:
        if not c:
            continue
        valid, _score, _reason = validar_nombre_compositor(c)
        if valid:
            return c
    return None


def classify_composer_name(name: str | None) -> str:
    """Clasifica un nombre de compositor de forma heurística.

    Devuelve:
    - "incorrect": sospechoso claro (patrones como "arranged from/by", "attributed to",
      "arr.", "by ", "[]", "&", "/", cifras, sin letras, una sola letra). Estos van a la
      lista de revisión manual (no se borran).
    - "correct": nombre limpio de persona (varias palabras, solo letras/espacio/apóstrofe/
      guión/punto/comilla, sin cifras ni patrones de ruido).
    - "not_reviewed": ambiguo (palabra única o caracteres no sencillos), sin veredicto aún.
    - "reviewed": no se emite aquí; lo fija la administración.

    Es un filtro agresivo y no garantiza la identidad canónica; la revisión final es manual.
    """
    s = (name or "").strip()
    if not s or len(s) < 2:
        return REVIEW_INCORRECT
    if not any(ch.isalpha() for ch in s):  # soporta cirílico, chino, japonés...
        return REVIEW_INCORRECT
    if is_mojibake(s):
        return REVIEW_INCORRECT  # texto corrupto por encoding: ir a revisión, no un compositor

    lower = s.lower()
    if any(p in lower for p in _NOISE_PATTERNS):
        return REVIEW_INCORRECT
    if any(ch in s for ch in _NOISE_CHARS):
        return REVIEW_INCORRECT
    if re.search(r"[0-9]", s):
        return REVIEW_INCORRECT

    if not _SIMPLE_NAME.match(s):
        return REVIEW_NOT_REVIEWED
    tokens = [t for t in re.split(r"[\s,]+", s) if t]
    if len(tokens) >= 2:
        return REVIEW_CORRECT
    return REVIEW_NOT_REVIEWED
