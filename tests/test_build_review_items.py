"""Tests de las claves lógicas de la capa de revisión (fase 015)."""

from __future__ import annotations

from scripts.build_review_items import build_decision_key, build_item_key, build_work_key


def test_work_key_cpdl() -> None:
    assert build_work_key("CPDL", "14615", None) == "CPDL:14615"


def test_work_key_pdmx_por_hash() -> None:
    assert build_work_key("PDMX", None, "QmbbhLwwmuKqA9MC1ULhojEMGxnxDobsZPJEo69N8nbgTw") == (
        "PDMX:QmbbhLwwmuKqA9MC1ULhojEMGxnxDobsZPJEo69N8nbgTw"
    )


def test_work_key_cpdl_tiene_prioridad_sobre_hash() -> None:
    assert build_work_key("CPDL", "3236", "hash") == "CPDL:3236"


def test_work_key_sin_datos() -> None:
    assert build_work_key("PDMX", None, None) is None
    assert build_work_key(None, None, None) is None


def test_item_y_decision_key_son_canonicas_y_no_nulas() -> None:
    assert build_item_key("identity_cluster", None, "name:m teschner") == "identity_cluster||name:m teschner|"
    assert build_item_key("work_attribution", "CPDL:14615", None) == "work_attribution|CPDL:14615||"
    assert build_decision_key("relation", "CPDL:14615", "name:charles wood", "arranger") == (
        "relation|CPDL:14615|name:charles wood|arranger"
    )


def test_decision_key_distingue_rol() -> None:
    uno = build_decision_key("relation", "CPDL:1", "name:x", "composer")
    dos = build_decision_key("relation", "CPDL:1", "name:x", "arranger")
    assert uno != dos


def test_claves_sin_caracteres_invisibles() -> None:
    """U+200E y similares colisionan en el índice único del catálogo: se quitan de las claves."""
    from application.services.import_person_parser import canonical_name_key

    assert canonical_name_key("name:rinaldo del mel\u200e") == "name:rinaldo del mel"
    assert canonical_name_key("name:rinaldo del mel\u200e") == canonical_name_key("name:rinaldo del mel")
    assert canonical_name_key(None) == ""
    assert build_item_key("identity_cluster", None, "name:x\u200e") == build_item_key(
        "identity_cluster", None, "name:x"
    )


def test_work_key_con_caracteres_invisibles() -> None:
    assert build_work_key("PDMX", None, "abc\u200e") == "PDMX:abc"


def test_claves_canonicas_colapsan_espacios_raros() -> None:
    from application.services.import_person_parser import canonical_name_key

    # U+2009 (thin space) y U+00A0 (nbsp) son invisibles para la colación pero no para el índice.
    assert canonical_name_key("name:a\u2009b") == "name:a b"
    assert canonical_name_key("name:a\u00a0b") == "name:a b"
    assert canonical_name_key("name:a   b") == "name:a b"
    assert canonical_name_key("name:\u2003a") == "name: a"
    assert canonical_name_key("name:a\u200bb") == "name:ab"  # ZWSP: ni separa ni cuenta
