"""Tests del aislamiento de botocore frente a la config AWS de la máquina."""

from __future__ import annotations

import os

import pytest
from infrastructure.providers.cloudflare_r2 import _ensure_boto_env


def test_ensure_boto_env_neutraliza_perfil(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_PROFILE", "default")
    monkeypatch.setenv("AWS_DEFAULT_PROFILE", "default")
    monkeypatch.delenv("AWS_CONFIG_FILE", raising=False)
    monkeypatch.delenv("AWS_SHARED_CREDENTIALS_FILE", raising=False)

    _ensure_boto_env()

    assert "AWS_PROFILE" not in os.environ
    assert "AWS_DEFAULT_PROFILE" not in os.environ
    assert os.environ["AWS_CONFIG_FILE"].endswith("_no_aws_config")
    assert os.environ["AWS_SHARED_CREDENTIALS_FILE"] == os.environ["AWS_CONFIG_FILE"]


def test_ensure_boto_env_respeta_config_explicita(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_CONFIG_FILE", "/tmp/aws-explicito")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/tmp/aws-explicito")

    _ensure_boto_env()

    assert os.environ["AWS_CONFIG_FILE"] == "/tmp/aws-explicito"
