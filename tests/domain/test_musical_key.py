"""Tests de la extracción determinista de tonalidad."""

from __future__ import annotations

import pytest
from domain.services.musical_key import find_tonalities, join_tonalities, strip_tonalities


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Prelude in D major", "D major"),
        ("Fugue in G minor", "G minor"),
        ("Sonata en mi menor", "E minor"),
        ("Prélude en ré majeur", "D major"),
        ("Choral d-Moll", "D minor"),
        ("Prelude in Bb major", "B♭ major"),
        ("Air in B-flat", "B♭"),
        ("Phrygian Mode D minor", "D minor (Phrygian)"),
        ("Dorian mode", "Dorian"),
        ("G major, E minor", "G major, E minor"),
    ],
)
def test_tonalidades(text: str, expected: str) -> None:
    assert join_tonalities(find_tonalities(text)) == expected


@pytest.mark.parametrize(
    "text",
    ["Psalm 23", "This is a minor issue", "A Minor Bird", "Mass for choir", "Bach 333"],
)
def test_sin_falsos_positivos(text: str) -> None:
    assert find_tonalities(text) == []


def test_strip_tonalities_conserva_el_resto() -> None:
    cleaned, spans = strip_tonalities("Prelude in D major for organ")

    assert cleaned == "Prelude for organ"
    assert [span.key for span in spans] == ["D major"]


def test_no_solapa_modo_y_tonalidad() -> None:
    spans = find_tonalities("Fantasia Phrygian Mode D minor")

    assert [span.key for span in spans] == ["D minor (Phrygian)"]
