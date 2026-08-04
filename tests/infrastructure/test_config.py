from __future__ import annotations

from infrastructure.config import Settings


def test_settings_loads_from_yaml_config_file(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "storage:\n"
        "  backend: google_drive\n"
        "  local:\n"
        "    root: data/files\n"
        "  google_drive:\n"
        "    credentials: secrets/g.json\n"
        "    folder_id: xyz\n"
        "mirror:\n"
        "  cache: data/cache\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OSAP_CONFIG", str(cfg))
    monkeypatch.delenv("OSAP_STORAGE_BACKEND", raising=False)

    settings = Settings()

    assert settings.storage_backend == "google_drive"
    assert settings.google_drive_credentials == "secrets/g.json"
    assert settings.google_drive_folder_id == "xyz"
    assert settings.mirror_cache == "data/cache"


def test_settings_defaults_when_no_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OSAP_CONFIG", str(tmp_path / "no-existe.yaml"))
    monkeypatch.delenv("OSAP_STORAGE_BACKEND", raising=False)

    settings = Settings()

    assert settings.storage_backend == "local"
    assert settings.storage_local_root == "data/files"
