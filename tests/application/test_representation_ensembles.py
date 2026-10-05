"""Tests de derivación del contexto de formación de una representación (Bloque 3)."""

from __future__ import annotations

from application.services.representation_ensembles import (
    derive_from_terms,
    voice_signature,
)


def test_voice_signature() -> None:
    assert voice_signature("SATB") == "S1A1T1B1"
    assert voice_signature("SSAATTBB") == "S2A2T2B2"
    assert voice_signature("TTBAR") == "T2BAR1"
    assert voice_signature(None) is None
    assert voice_signature("CHILDREN") is None


def test_derive_unico() -> None:
    assert derive_from_terms(["SATB", "SATB", " satb "]) == ("SATB", "S1A1T1B1")
    assert derive_from_terms(["S.A.T.B."]) == ("SATB", "S1A1T1B1")


def test_derive_ambiguo_o_vacio() -> None:
    assert derive_from_terms(["SATB", "STTB"]) == (None, None)
    assert derive_from_terms([]) == (None, None)
    assert derive_from_terms(["", "  "]) == (None, None)
    assert derive_from_terms(["BC"]) == (None, None)
    assert derive_from_terms(["MIXED"]) == (None, None)
