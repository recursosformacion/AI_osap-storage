from __future__ import annotations

from infrastructure.repositories.sql_person_repository import _parse_references


def test_texto_legado_separado_por_punto_y_coma() -> None:
    assert _parse_references("CPDL (ChoralWiki); Wikipedia") == [
        {"source": "CPDL (ChoralWiki)"},
        {"source": "Wikipedia"},
    ]


def test_json_de_lista_se_conserva() -> None:
    raw = '[{"source": "Grove", "url": "https://example.org/grove"}]'
    assert _parse_references(raw) == [
        {"source": "Grove", "url": "https://example.org/grove"}
    ]


def test_lista_con_cadenas_y_dicts() -> None:
    assert _parse_references(["VIAF", {"source": "IMSLP"}]) == [
        {"source": "VIAF"},
        {"source": "IMSLP"},
    ]


def test_vacio_y_nulo() -> None:
    assert _parse_references(None) == []
    assert _parse_references("   ") == []
    assert _parse_references("[]") == []
