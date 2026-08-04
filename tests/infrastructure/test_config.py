from __future__ import annotations

import pytest
from infrastructure.config import Settings
from pydantic import ValidationError


def _write_full_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "db:\n"
        "  host: 127.0.0.1\n"
        "  port: 3306\n"
        "  user: dev\n"
        "  password: devpass\n"
        "  name: osap_storage\n"
        "  pool_size: 10\n"
        "http:\n"
        "  host: 127.0.0.1\n"
        "  port: 8000\n"
        "  public_base_url: https://storage.openmusicrepository.com\n"
        "temp_dir: /tmp\n"
        "bootstrap:\n"
        "  create_default_provider: true\n"
        "repository:\n"
        "  provider: cloudflare_r2\n"
        "  cloudflare_r2:\n"
        "    bucket: pdmx\n"
        "    endpoint: https://acct.r2.cloudflarestorage.com\n"
        "    account_id: acct\n"
        "    access_key: key\n"
        "    secret_key: secret\n"
        "    public_url: https://cdn.openmusicrepository.com\n"
        "    path_prefix: pdmx\n"
        "    serve_directly: true\n"
        "providers:\n"
        "  pdmx:\n"
        "    source:\n"
        "      csv: data/pdmx/pdmx.csv\n",
        encoding="utf-8",
    )
    return str(cfg)


def test_settings_loads_from_yaml_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OSAP_CONFIG", _write_full_config(tmp_path))
    monkeypatch.delenv("OSAP_REPOSITORY_PROVIDER", raising=False)

    settings = Settings()

    assert settings.db_user == "dev"
    assert settings.repository_provider == "cloudflare_r2"
    assert settings.r2_bucket == "pdmx"
    assert settings.r2_public_url == "https://cdn.openmusicrepository.com"
    assert settings.r2_path_prefix == "pdmx"
    assert settings.r2_serve_directly is True
    assert settings.bootstrap_create_default_provider is True


def test_settings_requires_config_file(tmp_path, monkeypatch):
    # Sin fichero de configuración no debe haber valores por defecto en código
    monkeypatch.setenv("OSAP_CONFIG", str(tmp_path / "no-existe.yaml"))
    monkeypatch.delenv("OSAP_DB_USER", raising=False)

    with pytest.raises(ValidationError):
        Settings()
