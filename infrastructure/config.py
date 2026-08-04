from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class YamlConfigSource:
    """Carga la configuración desde un fichero YAML único (config.yaml)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def __call__(self) -> dict[str, Any]:
        return _load_yaml_config(self._path)


def _load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    storage = data.get("storage") or {}
    local = storage.get("local") or {}
    gdrive = storage.get("google_drive") or {}
    mirror = data.get("mirror") or {}
    pdmx = ((data.get("providers") or {}).get("pdmx") or {}).get("source") or {}

    cfg: dict[str, Any] = {}
    for key, value in {
        "storage_backend": storage.get("backend"),
        "storage_local_root": local.get("root"),
        "google_drive_credentials": gdrive.get("credentials"),
        "google_drive_folder_id": gdrive.get("folder_id"),
        "mirror_cache": mirror.get("cache"),
        "pdmx_source_csv": pdmx.get("csv"),
        "pdmx_source_zenodo_base_url": (pdmx.get("zenodo") or {}).get("base_url"),
    }.items():
        if value is not None:
            cfg[key] = value

    db = data.get("db") or {}
    for key in ("host", "port", "user", "password", "name", "pool_size"):
        field = f"db_{key}"
        if key in db:
            cfg[field] = db[key]

    http = data.get("http") or {}
    if "host" in http:
        cfg["http_host"] = http["host"]
    if "port" in http:
        cfg["http_port"] = http["port"]
    if "public_base_url" in http:
        cfg["public_base_url"] = http["public_base_url"]

    return cfg


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base de datos
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "osap"
    db_password: str = "osap"
    db_name: str = "osap_storage"
    db_pool_size: int = 10

    # HTTP
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    public_base_url: str = "http://localhost:8000"

    # Directorio temporal para descargas/materialización en curso
    temp_dir: str = "data/tmp"

    # Backend de almacenamiento activo (local | google_drive | s3)
    storage_backend: str = "local"
    storage_local_root: str = "data/files"
    google_drive_credentials: str | None = None
    google_drive_folder_id: str | None = None

    # Caché de mirrors (TARs descargados durante la ingesta offline)
    mirror_cache: str = "data/cache"
    keep_tar_after_materialize: bool = True

    # Fuente PDMX (ingesta offline)
    pdmx_source_csv: str | None = None
    pdmx_source_zenodo_base_url: str | None = None

    # Crear el proveedor por defecto según storage_backend al arrancar
    bootstrap_default_provider: bool = True

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ) -> tuple:
        config_path = Path(os.environ.get("OSAP_CONFIG", PROJECT_ROOT / "config.yaml"))
        # Prioridad: init > entorno > .env > config.yaml > secretos
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSource(config_path),
            file_secret_settings,
        )
