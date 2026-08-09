from __future__ import annotations

from domain.services.composer_names import normalize_composer_name


def test_empty_or_none_yields_empty():
    assert normalize_composer_name(None) == ""
    assert normalize_composer_name("") == ""
    assert normalize_composer_name("   ") == ""


def test_case_insensitive():
    assert normalize_composer_name("Wolfgang Amadeus Mozart") == "wolfgang amadeus mozart"


def test_trivial_spelling_differences_converge():
    assert normalize_composer_name("W. A. Mozart") == "w a mozart"
    assert normalize_composer_name("w. a. mozart") == "w a mozart"
    assert normalize_composer_name("W A Mozart") == "w a mozart"
    assert normalize_composer_name("w-a-mozart") == "w a mozart"


def test_repeated_and_trailing_spaces_collapse():
    assert normalize_composer_name("  W.  A.   Mozart  ") == "w a mozart"


def test_diacritics_removed():
    assert normalize_composer_name("José") == "jose"


def test_canonical_name_not_modified_by_normalization():
    # La normalización es solo para la búsqueda; el nombre original se conserva aparte.
    original = "W. A. Mozart"
    normalized = normalize_composer_name(original)
    assert original == "W. A. Mozart"
    assert normalized != original
