"""Tests del parser de nombres de import (paso 1 de la reconciliación de personas).

Casos tomados de datos reales de `works_person_import` en producción.
"""

from __future__ import annotations

import pytest
from application.services.import_person_parser import parse_import_name, role_id_for


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        ("anon.", "anonymous"),
        ("Anonymous", "anonymous"),
        ("anónimo", "anonymous"),
        ("Desconhecido", "anonymous"),
        ("Desconocido", "anonymous"),
        ("Traditional", "traditional"),
        ("tradicional", "traditional"),
        ("Volksweise", "traditional"),
        ("popular", "traditional"),
    ],
)
def test_atribuciones_no_personales(raw: str, status: str) -> None:
    row = parse_import_name(raw, "composer")

    assert row.kind == "attribution"
    assert row.attribution_status == status
    assert row.persons == []


@pytest.mark.parametrize("raw", ["Misc tunes", "na", "", "-", "Varios"])
def test_ruido_sin_autoria(raw: str) -> None:
    assert parse_import_name(raw, "composer").kind == "junk"


def test_persona_simple_usa_el_rol_del_import() -> None:
    row = parse_import_name("William James Kirkpatrick", "composer")

    assert row.kind == "person"
    assert [(p.name, p.role_key) for p in row.persons] == [("William James Kirkpatrick", "composer")]


def test_rol_explicito_de_arreglista() -> None:
    row = parse_import_name("Arranged by Ishbah Cox")

    assert row.kind == "person"
    assert [(p.name, p.role_key) for p in row.persons] == [("Ishbah Cox", "arranger")]


def test_dos_roles_en_una_cadena() -> None:
    row = parse_import_name("Composed by Toby Fox Arranged by Gonzalo Matus")

    assert row.kind == "person"
    assert [(p.name, p.role_key) for p in row.persons] == [
        ("Toby Fox", "composer"),
        ("Gonzalo Matus", "arranger"),
    ]


def test_tres_roles_en_una_cadena() -> None:
    row = parse_import_name(
        "Music by CHARLES H. GABRIEL (1856-1932)Arranged by KENNETH PADENAdapted by ROLLO DILWORTH"
    )

    assert row.kind == "person"
    roles = {p.role_key for p in row.persons}
    assert roles == {"composer", "arranger", "adapter"}
    assert any(p.name == "ROLLO DILWORTH" for p in row.persons)


def test_sufijo_entre_parentesis() -> None:
    row = parse_import_name("Koji Kondo / xMrPianox (Arranger)")

    assert row.kind == "person"
    assert [(p.name, p.role_key) for p in row.persons] == [("Koji Kondo", "composer"), ("xMrPianox", "arranger")] or [
        (p.name, p.role_key) for p in row.persons
    ] == [("xMrPianox", "arranger")]


def test_nombre_con_fechas_se_limpia() -> None:
    row = parse_import_name("Edward Patrick Crawford (1846-1912)", "composer")

    assert row.kind == "person"
    assert row.persons[0].name == "Edward Patrick Crawford"


def test_dos_personas_con_y() -> None:
    row = parse_import_name("Artie Resnick and Kenny Young", "composer")

    assert row.kind == "person"
    assert [p.name for p in row.persons] == ["Artie Resnick", "Kenny Young"]


def test_comp_abreviado() -> None:
    row = parse_import_name("Comp.Alexander Hume")

    assert row.kind == "person"
    assert [(p.name, p.role_key) for p in row.persons] == [("Alexander Hume", "composer")]


def test_compositor_desconocido_con_fecha() -> None:
    row = parse_import_name("Composer Unknown 1866")

    assert row.kind in ("person", "junk")
    assert all(p.name.lower() not in {"unknown", ""} for p in row.persons)


@pytest.mark.parametrize(
    "raw",
    [
        "77 77GENEVAN 136www.hymnary.org/text/let_us_with_a_gladsome_mind",
        "JCS/TAB",
        "M2U lyrics:NICODE vocal:M2U&guriri",
    ],
)
def test_no_parseables_no_generan_personas(raw: str) -> None:
    row = parse_import_name(raw, "composer")
    # O bien son varias piezas de texto con rol (lyrics/vocal) o bien basura: nunca una persona
    # con el texto tal cual.
    assert all(len(p.name.split()) <= 6 for p in row.persons)
    assert raw not in [p.name for p in row.persons]


def test_roles_tienen_id_de_catalogo() -> None:
    row = parse_import_name("Composed by Toby Fox Arranged by Gonzalo Matus")

    for person in row.persons:
        assert role_id_for(person.role_key) is not None


def test_artista_basura_no_es_persona() -> None:
    assert parse_import_name("Misc tunes", "artist").kind == "junk"
