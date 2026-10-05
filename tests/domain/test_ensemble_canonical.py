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
        ("B SOLO", "SOLO_B"),
        # Letras sueltas sin contexto: no son voz.
        ("A GLÄUBIGE SEELE", "UNSPECIFIED"),
        ("T EVANGELISTA", "UNSPECIFIED"),
        ("B JESUS", "UNSPECIFIED"),
        # BAR/BARB pegados ambiguos: no se fuerza una formación.
        ("TBARBARB", "UNKNOWN"),
        ("ATBARBARB", "UNKNOWN"),
        # Descriptores sin formación concreta.
        ("MIXED", "UNSPECIFIED"),
        ("DIV", "UNSPECIFIED"),
        ("VOICE", "UNSPECIFIED"),
        ("PARTSONG", "UNSPECIFIED"),
    ],
)
def test_canonical_id(raw: str, expected: str) -> None:
    assert canonical_id(raw) == expected, f"{raw!r} -> {canonical_id(raw)}"


def test_idempotencia() -> None:
    for raw in (
        "SATB", "SATB.SATB", "TTBARB", "SOLO SOPRANO", "UNISON_FEMALE", "SATB_SOLO_S",
        "CHILDREN", "FEMALE_CHOIR", "CANTOR_CONGREGATION", "SOLI_GROUP",
        "UNKNOWN", "INVALID_OR_INSTRUMENTAL", "UNSPECIFIED",
        "UNKNOWN|UNKNOWN", "UNSPECIFIED|SATB",
    ):
        once = canonical_id(raw)
        assert canonical_id(once) == once, f"{raw!r} -> {once!r} no idempotente"


def test_punto_fijo_tokenizacion() -> None:
    # La tokenización greedy producía ids no estables (AATBARB -> AATBAR); la función
    # itera a punto fijo para que `canonical_ensemble(id) == id`.
    assert canonical_id("AATBARBB") == "AATBAR"
    assert canonical_id("SATBARBB") == "SATBAR"
    assert canonical_id("SMZ") == "MZ"
    for raw in ("AATBARBB", "SATBARBB", "SMZ", "A_SOLO_S", "TTBARB"):
        once = canonical_id(raw)
        assert canonical_id(once) == once


def test_multibloque_sin_voces_hereda_centinela() -> None:
    info = canonical_ensemble("UNKNOWN|UNKNOWN")
    assert info.kind == "UNKNOWN"
    assert info.total_voices == 0
    assert canonical_ensemble("SATB|SATB").kind == "VOICES"


def test_descomposicion_y_familia() -> None:
    result = canonical_ensemble("SSAATTBB")
    assert result.kind == "VOICES"
    assert result.total_voices == 8
    assert result.family == "MIXED"
    assert result.voice_counts["S"] == 2
    assert result.voice_counts["B"] == 2
    assert "Soprano×2" in result.description


def test_invalid_descriptor_y_unknown() -> None:
    assert canonical_ensemble("BC").kind == "INVALID"
    assert canonical_ensemble("BC").total_voices == 0
    assert canonical_ensemble("MIXED").kind == "DESCRIPTOR"
    assert canonical_ensemble("LEADSHEET NOTES").kind == "DESCRIPTOR"
    assert canonical_ensemble("").kind == "DESCRIPTOR"
    assert canonical_ensemble("TBARBARB").kind == "UNKNOWN"


def test_tipo_retorno() -> None:
    assert isinstance(canonical_ensemble("SATB"), CanonicalEnsemble)
