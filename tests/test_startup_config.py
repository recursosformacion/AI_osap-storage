"""Tests de la validación de configuración de arranque de osap-storage (S1, fail-closed).

Sustituye al contrato roto del validador compartido (`osap.bootstrap...`) por validación
local: en producción (o sin marca de entorno) falla cerrado; en desarrollo/test avisa.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from infrastructure.config import (
    missing_required_keys,
    resolve_config_env,
    validate_startup_config,
)

_VALID: dict[str, object] = {
    "app": {"env": "production"},
    "db": {"host": "db", "name": "osap_storage", "user": "osap", "password": "secret"},
    "repository": {"provider": "local"},
}


def _write(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OSAP_ENV", raising=False)


def test_configuracion_valida_en_produccion_arranca(tmp_path: Path) -> None:
    validate_startup_config(_write(tmp_path, _VALID))


@pytest.mark.parametrize(
    "path",
    ["db.host", "db.name", "db.user", "db.password", "repository.provider"],
)
def test_cada_clave_obligatoria_ausente_no_arranca(tmp_path: Path, path: str) -> None:
    data = {k: dict(v) if isinstance(v, dict) else v for k, v in _VALID.items()}
    section, key = path.split(".")
    del data[section][key]  # type: ignore[index]
    with pytest.raises(SystemExit):
        validate_startup_config(_write(tmp_path, data))


def test_clave_vacia_no_arranca(tmp_path: Path) -> None:
    data = {k: dict(v) if isinstance(v, dict) else v for k, v in _VALID.items()}
    data["db"]["password"] = "   "  # type: ignore[index]
    with pytest.raises(SystemExit):
        validate_startup_config(_write(tmp_path, data))


def test_sin_marca_de_entorno_falla_cerrado(tmp_path: Path) -> None:
    # Sin OSAP_ENV ni app.env, se asume producción: no puede colarse el camino silencioso.
    data = {"db": {"host": "db"}, "repository": {}}
    with pytest.raises(SystemExit):
        validate_startup_config(_write(tmp_path, data))


def test_desarrollo_avisa_pero_arranca(tmp_path: Path) -> None:
    data = {"app": {"env": "development"}, "db": {}, "repository": {}}
    validate_startup_config(_write(tmp_path, data))


def test_osap_env_tiene_prioridad(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSAP_ENV", "development")
    data = {"app": {"env": "production"}, "db": {}, "repository": {}}
    validate_startup_config(_write(tmp_path, data))


def test_helpers_de_introspeccion() -> None:
    assert resolve_config_env({"app": {"env": "test"}}) == "test"
    assert resolve_config_env({}) == "production"
    assert missing_required_keys(_VALID) == []
