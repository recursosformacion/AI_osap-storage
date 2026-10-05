"""Tests de la función canónica de formaciones vocales."""

from __future__ import annotations

import pytest
from domain.services.ensemble_canonical import (
    CanonicalEnsemble,
    canonical_ensemble,
    canonical_id,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SATB", "SATB"),
        ("S.A.T.B.", "SATB"),
        ("SATB.SATB", "SATB|SATB"),
        ("SSAATTBB", "SSAATTBB"),
        ("AATTBB", "AATTBB"),
        ("TTBB", "TTBB"),
        ("TTBARB", "TTBAR"),
        ("SMZATB", "MZATB"),
        ("SAB", "SAB"),
        ("SSAA", "SSAA"),
        ("C-A'", "INVALID_OR_INSTRUMENTAL"),
        ("BC", "INVALID_OR_INSTRUMENTAL"),
        ("F4", "INVALID_OR_INSTRUMENTAL"),
        ("SOLO SOPRANO", "SOLO_S"),
        ("SATB + SOLO SOPRANO", "SATB_SOLO_S"),
        ("SATB SOLI", "SATB_SOLO"),
        ("UNISON", "UNISON"),
        ("UNISON FEMALE", "UNISON_FEMALE"),
        ("CHILDREN'S CHOIR", "CHILDREN"),
        ("TREBLE", "TREBLE"),
        ("A cappella SATB", "SATB"),
    ],
)
def test_canonical_id(raw: str, expected: str) -> None:
    assert canonical_id(raw) == expected, f"{raw!r} -> {canonical_id(raw)}"


def test_idempotencia() -> None:
    for raw in ("SATB", "SATB.SATB", "TTBARB", "SOLO SOPRANO", "UNISON_FEMALE", "SATB_SOLO_S"):
        once = canonical_id(raw)
        assert canonical_id(once) == once


def test_descomposicion_y_familia() -> None:
    result = canonical_ensemble("SSAATTBB")
    assert result.kind == "VOICES"
    assert result.total_voices == 8
    assert result.family == "MIXED"
    assert result.voice_counts["S"] == 2
    assert result.voice_counts["B"] == 2
    assert "Soprano×2" in result.description


def test_invalid_y_unknown() -> None:
    invalido = canonical_ensemble("BC")
    assert invalido.kind == "INVALID"
    assert invalido.total_voices == 0

    desconocido = canonical_ensemble("LEADSHEET NOTES")
    assert desconocido.kind == "UNKNOWN"

    vacio = canonical_ensemble("")
    assert vacio.kind == "UNKNOWN"


def test_tipo_retorno() -> None:
    assert isinstance(canonical_ensemble("SATB"), CanonicalEnsemble)
