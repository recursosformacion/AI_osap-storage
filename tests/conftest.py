from __future__ import annotations

import pytest
from infrastructure.config import Settings


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    """Config de test aislada: `OSAP_CONFIG` se restaura al terminar el test."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "db:\n  host: 127.0.0.1\n  port: 3306\n  user: dev\n  password: devpass\n"
        "  name: osap_storage\n  pool_size: 10\n"
        "http:\n  host: 127.0.0.1\n  port: 8000\n  public_base_url: http://storage.example\n"
        "temp_dir: /tmp\nbootstrap:\n  create_default_provider: false\n"
        "repository:\n  provider: local\n  local:\n    root: /tmp/data\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OSAP_CONFIG", str(cfg))
    monkeypatch.delenv("OSAP_REPOSITORY_PROVIDER", raising=False)
    return Settings()  # type: ignore[call-arg]
