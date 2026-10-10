"""Tests del importador de IMSLP (parseo y normalización del Worklist API)."""

from __future__ import annotations

from scripts.import_imslp_works import _parse_entry, _reverse_last_first


def test_reverse_last_first_normaliza_orden() -> None:
    assert _reverse_last_first("Ferrari, Carlotta") == "Carlotta Ferrari"
    assert _reverse_last_first("Mozart") == "Mozart"
    assert _reverse_last_first("  ") == ""


def test_parse_entry_normaliza_campos() -> None:
    entry = {
        "intvals": {
            "worktitle": '"A"',
            "composer": "Ferrari, Carlotta",
            "icatno": "ICF 1237",
            "pageid": "1637322",
        },
        "permlink": 'https://imslp.org/wiki/"A"_(Ferrari,_Carlotta)',
    }
    assert _parse_entry(entry) == {
        "pageid": "1637322",
        "title": '"A"',
        "composer": "Carlotta Ferrari",
        "catalogue": "ICF 1237",
        "source_url": 'https://imslp.org/wiki/"A"_(Ferrari,_Carlotta)',
    }


def test_parse_entry_descarta_entradas_invalidas() -> None:
    assert _parse_entry({"intvals": {"pageid": "1"}}) is None  # sin título
    assert _parse_entry({"intvals": {"worktitle": "X"}}) is None  # sin pageid
    assert _parse_entry("no soy un dict") is None
    assert _parse_entry({"intvals": None}) is None


def test_parse_entry_campos_opcionales_vacios_son_none() -> None:
    rec = _parse_entry({"intvals": {"worktitle": "Obra", "pageid": "9", "icatno": ""}})
    assert rec is not None
    assert rec["catalogue"] is None
    assert rec["source_url"] is None
    assert rec["composer"] is None
