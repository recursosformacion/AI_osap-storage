from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from resolve_persons import clean_name, is_resolvable_name  # noqa: E402


def test_nombres_vacios_o_solo_signos_no_crean_persona() -> None:
    for raw in ("", "   ", "?", "???", "- -", "...", "1234", "(?)"):
        assert is_resolvable_name(raw) is False


def test_anonimos_y_tradicionales_no_crean_persona() -> None:
    for raw in ("Anonymous", "anon.", "Trad.", "traditional", "Urheber unbekannt"):
        assert is_resolvable_name(raw) is False


def test_nombres_reales_si_se_resuelven() -> None:
    for raw in ("J. S. Bach", "Mozart", "Anónimo castellano", "李子", "O'Connor"):
        assert is_resolvable_name(raw) is True


def test_quita_titulo_entrecomillado_pegado_al_nombre() -> None:
    assert clean_name("'A Reel'Abraham MacIntosh 1792") == "Abraham MacIntosh"


def test_conserva_apodos_con_espacio() -> None:
    assert clean_name("'Blue' Fisher") == "'Blue' Fisher"
