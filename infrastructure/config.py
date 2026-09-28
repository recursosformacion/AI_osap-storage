from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)

# Claves obligatorias en producción. Sin estas, el servicio no debe arrancar (fail-closed).
_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "db": ("host", "name", "user", "password"),
    "repository": ("provider",),
}


def resolve_config_env(data: dict[str, Any]) -> str:
    """Entorno efectivo: `OSAP_ENV` > `app.env` del YAML > production (fail-closed)."""
    explicit = os.environ.get("OSAP_ENV", "").strip().lower()
    if explicit:
        return explicit
    app = data.get("app")
    if isinstance(app, dict):
        value = app.get("env")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return "production"


def missing_required_keys(data: dict[str, Any]) -> list[str]:
    """Devuelve las claves obligatorias ausentes o vacías (`seccion.clave`)."""
    missing: list[str] = []
    for section, keys in _REQUIRED_KEYS.items():
        block = data.get(section)
        for key in keys:
            value = block.get(key) if isinstance(block, dict) else None
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(f"{section}.{key}")
    return missing


def auth_enabled_value(data: dict[str, Any]) -> bool | None:
    """Valor de `auth.enabled` leído del YAML, o `None` si no está declarado."""
    auth = data.get("auth")
    if isinstance(auth, dict):
        value = auth.get("enabled")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return None


def validate_startup_config(config_path: Path | None = None) -> None:
    """Valida la configuración al arrancar.

    En producción (o si no hay marca explícita de entorno) falla cerrado ante cualquier
    clave obligatoria ausente y exige `auth.enabled: true`; en desarrollo/test solo avisa
    y permite `auth.enabled: false` de forma explícita.
    """
    path = config_path or Path(os.environ.get("OSAP_CONFIG", PROJECT_ROOT / "config.yaml"))
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    env = resolve_config_env(data)
    errors = missing_required_keys(data)
    if env == "production" and auth_enabled_value(data) is not True:
        errors.append("auth.enabled (debe ser true en producción)")
    if env == "production" and errors:
        raise SystemExit(
            f"[osap-storage] configuración inválida ({path}): {', '.join(errors)}"
        )
    if errors:
        logger.warning("[osap-storage] configuración incompleta (%s): %s", path, ", ".join(errors))



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

    cfg: dict[str, Any] = {}

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

    if "temp_dir" in data:
        cfg["temp_dir"] = data["temp_dir"]

    repository = data.get("repository") or {}
    if "provider" in repository:
        cfg["repository_provider"] = repository["provider"]
    local = repository.get("local") or {}
    if "root" in local:
        cfg["repository_local_root"] = local["root"]
    r2 = repository.get("cloudflare_r2") or {}
    for key, field in {
        "bucket": "r2_bucket",
        "endpoint": "r2_endpoint",
        "account_id": "r2_account_id",
        "access_key": "r2_access_key",
        "secret_key": "r2_secret_key",
        "public_url": "r2_public_url",
        "path_prefix": "r2_path_prefix",
        "serve_directly": "r2_serve_directly",
    }.items():
        if key in r2:
            cfg[field] = r2[key]

    bootstrap = data.get("bootstrap") or {}
    if "create_default_provider" in bootstrap:
        cfg["bootstrap_create_default_provider"] = bootstrap["create_default_provider"]

    auth = data.get("auth") or {}
    for key, field in {
        "enabled": "auth_enabled",
        "issuer": "auth_issuer",
        "audience": "auth_audience",
        "jwks_url": "auth_jwks_url",
        "public_key": "auth_public_key",
        "kid": "auth_kid",
        "clock_skew_seconds": "auth_clock_skew_seconds",
    }.items():
        if key in auth:
            cfg[field] = auth[key]

    osap_api = data.get("osap_api") or {}
    if "base_url" in osap_api:
        cfg["osap_api_base_url"] = osap_api["base_url"]
    if "service_token" in osap_api:
        cfg["osap_api_service_token"] = osap_api["service_token"]

    metabrainz = data.get("metabrainz") or {}
    if "token" in metabrainz:
        cfg["metabrainz_token"] = metabrainz["token"]
    if "base_url" in metabrainz:
        cfg["metabrainz_base_url"] = metabrainz["base_url"]
    if "tmp_dir" in metabrainz:
        cfg["metabrainz_tmp_dir"] = metabrainz["tmp_dir"]

    pdmx = ((data.get("providers") or {}).get("pdmx") or {}).get("source") or {}
    if "csv" in pdmx:
        cfg["pdmx_source_csv"] = pdmx["csv"]
    if (pdmx.get("zenodo") or {}).get("base_url"):
        cfg["pdmx_source_zenodo_base_url"] = pdmx["zenodo"]["base_url"]

    return cfg


class Settings(BaseSettings):
    """Esquema de configuración. Sin valores por defecto: TODO viene de config.yaml.

    El fichero activo se elige con OSAP_CONFIG (por defecto config.yaml en la raíz).
    Este módulo solo define el esquema; ningún valor de configuración vive en código.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # Base de datos
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    db_pool_size: int

    # HTTP
    http_host: str
    http_port: int
    public_base_url: str

    # Directorio temporal para descargas/materialización en curso
    temp_dir: str

    # Repositorio oficial (no "backend"): local | cloudflare_r2
    repository_provider: str
    repository_local_root: str = ""
    r2_bucket: str = ""
    r2_endpoint: str = ""
    r2_account_id: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_public_url: str | None = None
    r2_path_prefix: str = ""
    r2_serve_directly: bool = False

    # Fuente PDMX (ingesta offline)
    pdmx_source_csv: str | None = None
    pdmx_source_zenodo_base_url: str | None = None

    # Crear el proveedor por defecto según repository.provider al arrancar
    bootstrap_create_default_provider: bool

    # Autenticación de servicio (service-auth-v1). Desactivada por defecto hasta desplegar.
    auth_enabled: bool = True
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""
    auth_public_key: str = ""
    auth_kid: str = ""
    auth_clock_skew_seconds: int = 60

    # osap-api (especialista en resolución de entidades externas). Storage llama a su
    # POST /api/v1/composers/resolve y procesa la respuesta.
    osap_api_base_url: str = "https://app.openmusicrepository.com"
    osap_api_service_token: str | None = None

    # Metabrainz (replicación MusicBrainz) para sincronizar la autoridad de compositores.
    # El token NO vive en el código: se configura en config.yaml / config.production.yaml.
    metabrainz_token: str | None = None
    metabrainz_base_url: str = "https://metabrainz.org/api/musicbrainz/replication-info"
    metabrainz_tmp_dir: str = ""

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
        # Prioridad: init > variables de entorno > config.yaml > secretos
        return (
            init_settings,
            env_settings,
            YamlConfigSource(config_path),
            file_secret_settings,
        )
