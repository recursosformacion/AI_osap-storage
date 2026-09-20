from __future__ import annotations

from domain.services.composer_names import normalize_composer_name

# Palabras funcionales y términos musicales genéricos: no cuentan como evidencia por sí solos.
STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "from", "by",
    "de", "la", "el", "los", "las", "le", "les", "du", "des", "un", "une", "et", "en",
    "sur", "avec", "von", "der", "die", "das", "und", "il", "lo", "gli", "con", "per", "su",
    "del", "della", "di", "al", "alla", "nel", "nella", "se", "no", "op", "bwv", "k", "wab",
}
GENERIC = {
    "gavotte", "gavottes", "air", "aire", "aires", "aria", "arias", "mass", "masses", "messe",
    "missa", "messas", "africa", "dance", "dances", "sonata", "sonatas", "sonate", "allegro",
    "adagio", "andante", "prelude", "preludes", "waltz", "waltzes", "march", "marches", "hymn",
    "hymns", "song", "songs", "motet", "motets", "madrigal", "madrigals", "allemande",
    "courante", "sarabande", "gigue", "menuet", "minuet", "fugue", "fugues", "toccata",
    "canzona", "ricercar", "theme", "themes", "variations", "var", "excerpts", "excerpt",
}


def significant_tokens(text: str | None) -> frozenset[str]:
    """Tokens con valor probatorio (ni funcionales ni genéricos musicales)."""
    return frozenset(
        token for token in normalize_composer_name(text).split()
        if len(token) >= 3 and token not in STOPWORDS and token not in GENERIC
    )


def is_attributable_title(title: str | None) -> bool:
    """Un título de un solo token significativo no es base para atribución automática."""
    return len(significant_tokens(title)) >= 2
