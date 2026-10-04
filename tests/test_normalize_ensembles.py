"""Regresión de `normalize_ensembles.canonical_code` (origen de los artefactos).

Cubre: espacios intra-formación (`SA T B` -> `SATB`), multi-coro preservando `.`,
descriptivos y notación vocal válida intacta.
"""

from __future__ import annotations

from scripts.normalize_ensembles import canonical_code, is_voice_block


def test_espacios_intra_formacion_se_colapsan() -> None:
    assert canonical_code("SA T B") == "SATB"
    assert canonical_code("satb") == "SATB"
    assert canonical_code("S S ATB") == "SSATB"
    assert canonical_code("saatb") == "SAATB"


def test_multicoro_preserva_punto() -> None:
    assert canonical_code("SATB.SATB") == "SATB.SATB"
    assert canonical_code("SATB-SATB") == "SATB.SATB"
    assert canonical_code("SATB / SATB") == "SATB.SATB"


def test_notacion_vocal_valida_intacta() -> None:
    assert canonical_code("SATB") == "SATB"
    assert canonical_code("AATTB") == "AATTB"
    assert canonical_code("SATBARB") == "SATBARB"


def test_descriptivos_se_normalizan_con_espacio() -> None:
    assert canonical_code("SOLO MEZZO-SOPRANO") == "SOLO MEZZO SOPRANO"
    assert canonical_code("A_CAPP") == "A CAPP"


def test_is_voice_block() -> None:
    assert is_voice_block("SATB")
    assert is_voice_block("BAR")
    assert not is_voice_block("SOLO")
