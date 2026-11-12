"""Tests del buscador de instrumentos sobre el vocabulario inyectado."""

from __future__ import annotations

from application.services.instrument_vocabulary import InstrumentVocabulary, normalize_term

ROWS = [
    {
        "code": "tuba",
        "name_en": "Tuba",
        "name_es": "Tuba",
        "aliases": '["Bombardino"]',
    },
    {
        "code": "flute",
        "name_en": "Flute",
        "name_es": "Flauta",
        "aliases": '["Flauta travesera"]',
        "imslp_codes": '["fl"]',
    },
    {
        "code": "bass",
        "name_en": "Bass",
        "name_es": "Bajo",
        "aliases": None,
    },
]


def test_normaliza_acentos_y_puntuacion() -> None:
    assert normalize_term("Flauta  Traviesa, en Do") == "flauta traviesa en do"


def test_encuentra_alias_y_nombre_espanol() -> None:
    vocabulary = InstrumentVocabulary.from_rows(ROWS)

    codes = [match.code for match in vocabulary.find("Gran Vals for Tuba duet")]
    assert codes == ["tuba"]
    assert [match.code for match in vocabulary.find("para flauta travesera")] == ["flute"]


def test_no_coincide_dentro_de_otra_palabra() -> None:
    vocabulary = InstrumentVocabulary.from_rows(ROWS)

    assert vocabulary.find("contrabassoon") == []


def test_deduplica_por_codigo() -> None:
    vocabulary = InstrumentVocabulary.from_rows(ROWS)

    matches = vocabulary.find("Bass and bajo")
    assert [match.code for match in matches] == ["bass"]


def test_vacio_si_no_hay_vocabulario() -> None:
    vocabulary = InstrumentVocabulary.from_rows([])

    assert not vocabulary
    assert vocabulary.find("for piano") == []
