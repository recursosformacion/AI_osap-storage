"""Tests del extractor unificado de metadatos (datos reales de catálogo)."""

from __future__ import annotations

from application.services.instrument_vocabulary import InstrumentVocabulary
from application.services.metadata_extractor import extract_metadata

VOCABULARY = InstrumentVocabulary.from_rows(
    [
        {"code": "tuba", "name_en": "Tuba", "name_es": "Tuba"},
        {"code": "guitar", "name_en": "Guitar", "name_es": "Guitarra"},
        {"code": "piano", "name_en": "Piano", "name_es": "Piano"},
    ]
)


def test_credito_entre_parentesis() -> None:
    result = extract_metadata("Ave Maria (Bach, Johann Sebastian)")

    assert result.title == "Ave Maria"
    assert [(person.name, person.role) for person in result.persons] == [
        ("Bach, Johann Sebastian", "composer")
    ]


def test_credito_tras_by_y_formacion() -> None:
    result = extract_metadata(
        "Gran Vals by Francisco Tárrega for Tuba duet", instrument_vocabulary=VOCABULARY
    )

    assert result.title == "Gran Vals"
    assert result.composer is not None
    assert result.composer.name == "Francisco Tárrega"
    assert [item.code for item in result.instruments] == ["tuba"]


def test_arreglista_y_atribucion_tradicional() -> None:
    result = extract_metadata("Traditional carol arr. John Rutter")

    assert result.attribution == "traditional"
    assert [(person.name, person.role) for person in result.persons] == [
        ("John Rutter", "arranger")
    ]
    assert "mixed_credit_and_attribution" in result.flags


def test_compositor_previo_y_orquestador() -> None:
    result = extract_metadata(
        "Peter I. Tchaikovsky - Italian Song (Orchestra) Orchestrated by Alex Nuñez"
    )

    assert result.title == "Italian Song"
    assert [(person.name, person.role) for person in result.persons] == [
        ("Peter I. Tchaikovsky", "composer"),
        ("Alex Nuñez", "orchestrator"),
    ]
    assert [item.code for item in result.ensembles] == ["INSTRUMENTAL_ORCH"]


def test_compositor_antes_de_dos_puntos() -> None:
    result = extract_metadata(
        "Cristobal Tapia de Veer: Utopia Theme - A Piano Arrangement by melodyREDACTED",
        instrument_vocabulary=VOCABULARY,
    )

    assert result.title == "Utopia Theme"
    assert [(person.name, person.role) for person in result.persons] == [
        ("Cristobal Tapia de Veer", "composer"),
        ("melodyREDACTED", "arranger"),
    ]
    assert [item.code for item in result.instruments] == ["piano"]


def test_transcriptor_y_credito_entre_parentesis() -> None:
    result = extract_metadata(
        "Tamourin (Royer, J. N. P.) - guitar transcription by Artiom Galuza",
        instrument_vocabulary=VOCABULARY,
    )

    assert result.title == "Tamourin"
    assert [(person.role, person.name) for person in result.persons] == [
        ("composer", "Royer, J. N. P"),
        ("transcriber", "Artiom Galuza"),
    ]


def test_tonalidad_y_titulo() -> None:
    result = extract_metadata("Prelude in D major for organ")

    assert result.title == "Prelude for organ"
    assert result.key == "D major"


def test_codigos_de_fuente_y_repes() -> None:
    assert extract_metadata("Oddfellows Holiday. HS.09").title == "Oddfellows Holiday"
    assert extract_metadata("The High Reel 2x").title == "The High Reel"
    assert extract_metadata("Psalm 23").title == "Psalm 23"
    assert extract_metadata("Genevan 136").title == "Genevan 136"


def test_guion_sin_credito_no_recorta_el_titulo() -> None:
    result = extract_metadata("Crimson Peak - Edith's Theme")

    assert result.title == "Crimson Peak - Edith's Theme"
    assert result.persons == ()


def test_credito_tras_guion_solo_con_marca_o_catalogo() -> None:
    ambiguous = extract_metadata("Genevan 136 - Pierre Davantès")
    known = extract_metadata(
        "Genevan 136 - Pierre Davantès",
        known_person=lambda name: name == "Pierre Davantès",
    )

    assert ambiguous.persons == ()
    assert ambiguous.title == "Genevan 136 - Pierre Davantès"
    assert [(person.name, person.role) for person in known.persons] == [
        ("Pierre Davantès", "composer")
    ]
    assert known.title == "Genevan 136"


def test_parcial_tematico_entre_parentesis_no_es_credito() -> None:
    result = extract_metadata("A Christmas Lullaby (Sleep, baby, sleep)")

    assert result.title == "A Christmas Lullaby (Sleep, baby, sleep)"
    assert result.persons == ()


def test_no_confunde_psalmus_con_codigo() -> None:
    result = extract_metadata("A 25 : Ps. 144 : Proche est le Seigneur")

    assert result.title == "A 25: Ps. 144: Proche est le Seigneur"
    assert extract_metadata("E se fur già, PdPWV Mad078").title == (
        "E se fur già, PdPWV Mad078"
    )


def test_opus_catalogo_y_anos() -> None:
    result = extract_metadata("Und ich sah, Op.59 (1846-1912)")

    assert result.opus == "Op.59"
    assert result.year_from == 1846
    assert result.year_to == 1912
    assert result.year is None


def test_formacion_vocal_en_parentesis() -> None:
    result = extract_metadata("Missa brevis (SATB)")

    assert result.title == "Missa brevis"
    assert [item.code for item in result.ensembles] == ["SATB"]


def test_texto_vacio() -> None:
    result = extract_metadata(None)

    assert result.title == ""
    assert result.flags == ("empty_text",)


def test_html_entities_y_xml() -> None:
    result = extract_metadata("Christ rising again &ndash; Christ is risen again")

    assert result.title == "Christ rising again"
    assert result.subtitle == "Christ is risen again"
