"""Tests del normalizador de voicing CPDL (`application.services.cpdl_voicing`).

Demuestran que un registro CPDL con varios voicings sigue siendo UN registro y que los
términos derivados permiten buscar cada voicing por separado con coincidencia exacta.
"""

from __future__ import annotations

import json

from application.services.cpdl_voicing import normalize_term, voicing_terms


def _arr(items: list[str]) -> str:
    return json.dumps(items, ensure_ascii=False)


def test_caso_simple_satb():
    terms = voicing_terms(_arr(["4", "SATB"]))
    assert terms == ["SATB"]


def test_caso_multi_voicing_cuatro_terminos():
    # ["4", "SATB, STTB, AATB, ATTB"] -> un registro, 4 términos buscables.
    terms = voicing_terms(_arr(["4", "SATB, STTB, AATB, ATTB"]))
    assert len(terms) == 4
    assert terms == ["SATB", "STTB", "AATB", "ATTB"]
    # Sin duplicados por voicing: 4 términos, no 4 registros (eso lo garantiza la BD).
    assert len(set(terms)) == 4


def test_separadores_variados():
    # Sin espacio tras la coma (también real en CPDL).
    assert voicing_terms(_arr(["4", "SATB,ATTB"])) == ["SATB", "ATTB"]
    assert voicing_terms(_arr(["4", "SATB, TTBB, AATB"])) == ["SATB", "TTBB", "AATB"]


def test_elemento_numero_descartado():
    # El primer elemento (número de voces) no se convierte en término de búsqueda.
    assert "4" not in voicing_terms(_arr(["4", "SATB"]))
    # Rangos no fiables tampoco.
    assert voicing_terms(_arr(["4 or 5", "SATB, SATTB"])) == ["SATB", "SATTB"]
    assert voicing_terms(_arr(["4/5", "ATTB,SATB"])) == ["ATTB", "SATB"]


def test_no_falso_positivo_subcadena():
    terms = voicing_terms(_arr(["4", "SATB, SATB2"]))
    assert "SATB" in terms
    assert "SATB2" in terms
    # Buscar SATB no debe resolverse como SATB2: la comparación es por token exacto.
    assert normalize_term("SATB") not in {normalize_term("SATB2")}


def test_case_insensitive():
    assert voicing_terms(_arr(["4", "satb"])) == ["SATB"]
    assert normalize_term("satb") == normalize_term("SATB") == normalize_term("Satb")


def test_vacios_null_y_sin_voicing():
    assert voicing_terms(None) == []
    assert voicing_terms("") == []
    assert voicing_terms("[]") == []
    assert voicing_terms("null") == []
    assert voicing_terms("no-json") == []
    assert voicing_terms(_arr([])) == []


def test_ruido_de_plantillas_descartado():
    # Elementos residuales del parser (add=..., {{Cat...) no deben ser buscables.
    terms = voicing_terms(_arr(["4 or 3", "SATB", "add={{Vcat", "SAB"]))
    assert terms == ["SATB", "SAB"]


def test_tokens_especiales_conservados():
    # "SATB.SATB" (doble coro) se conserva como token propio, sin falsear SATB.
    terms = voicing_terms(_arr(["8", "SATB.SATB"]))
    assert "SATB.SATB" in terms
    assert normalize_term("SATB") not in {normalize_term("SATB.SATB")}
    # "S,T" (soprano y tenor como líneas separadas) produce dos tokens: S y T.
    solo = voicing_terms(_arr(["1", "S,T"]))
    assert set(solo) == {"S", "T"}


def test_textos_de_solo_no_duplican():
    # "Solo Soprano"/"Solo high" son un único token descriptivo.
    assert voicing_terms(_arr(["1", "Solo Soprano"])) == ["SOLO SOPRANO"]
