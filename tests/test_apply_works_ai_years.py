"""Normalización de años del pipeline AI antes de escribir en `works`."""

from __future__ import annotations

from scripts.apply_works_ai_json import normalize_year_fields


def test_rango_en_year_se_convierte_en_from_to() -> None:
    row = normalize_year_fields({"year": "1727-1807"})

    assert row["year"] is None
    assert row["year_from"] == 1727
    assert row["year_to"] == 1807


def test_ano_simple_se_conserva() -> None:
    row = normalize_year_fields({"year": "1816"})

    assert row["year"] == 1816
    assert row["year_from"] is None
    assert row["year_to"] is None


def test_texto_dudoso_se_descarta() -> None:
    row = normalize_year_fields({"year": "c. 1750"})

    assert row["year"] is None
    assert row["year_from"] is None
    assert row["year_to"] is None


def test_from_to_explicitos_tienen_prioridad() -> None:
    row = normalize_year_fields(
        {"year": "1727-1807", "year_from": "1700", "year_to": "1710"}
    )

    assert row["year"] is None
    assert row["year_from"] == 1700
    assert row["year_to"] == 1710
