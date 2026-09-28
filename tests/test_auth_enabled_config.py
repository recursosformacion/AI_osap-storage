"""Tests de S2: `auth_enabled` fail-closed en producción (osap-storage).

En producción la autenticación de servicio no puede quedar desactivada ni por defecto ni
por omisión; en desarrollo/test debe poder desactivarse explícitamente.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from infrastructure.config import auth_enabled_value, validate_startup_config

_BASE: dict[str, object] = {
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


def test_production_con_auth_true_arranca(tmp_path: Path) -> None:
    data = {**_BASE, "app": {"env": "production"}, "auth": {"enabled": True}}
    validate_startup_config(_write(tmp_path, data))


def test_production_con_auth_false_no_arranca(tmp_path: Path) -> None:
    data = {**_BASE, "app": {"env": "production"}, "auth": {"enabled": False}}
    with pytest.raises(SystemExit):
        validate_startup_config(_write(tmp_path, data))


def test_production_sin_auth_no_arranca(tmp_path: Path) -> None:
    data = {**_BASE, "app": {"env": "production"}}
    with pytest.raises(SystemExit):
        validate_startup_config(_write(tmp_path, data))


def test_development_con_auth_false_arranca(tmp_path: Path) -> None:
    data = {**_BASE, "app": {"env": "development"}, "auth": {"enabled": False}}
    validate_startup_config(_write(tmp_path, data))


def test_test_con_auth_false_arranca(tmp_path: Path) -> None:
    data = {**_BASE, "app": {"env": "test"}, "auth": {"enabled": False}}
    validate_startup_config(_write(tmp_path, data))


def test_auth_enabled_value_acepta_bool_y_texto() -> None:
    assert auth_enabled_value({"auth": {"enabled": True}}) is True
    assert auth_enabled_value({"auth": {"enabled": "true"}}) is True
    assert auth_enabled_value({"auth": {"enabled": "false"}}) is False
    assert auth_enabled_value({"auth": {}}) is None
    assert auth_enabled_value({}) is None
