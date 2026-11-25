from types import SimpleNamespace

from api.urls import build_resource_url


def _settings(**overrides):
    base = SimpleNamespace(
        r2_serve_directly=True,
        r2_public_url="https://cdn.example",
        r2_path_prefix="",
        public_base_url="https://storage.example",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_build_resource_url_sin_ruta_cae_al_file_id() -> None:
    url, available = build_resource_url(None, 42, _settings())
    assert available is True
    assert url == "https://storage.example/api/v1/files/42/content"


def test_build_resource_url_sin_ruta_ni_file_id() -> None:
    assert build_resource_url(None, None, _settings()) == (None, False)


def test_build_resource_url_con_ruta() -> None:
    url, available = build_resource_url("mxl/a.mxl", None, _settings())
    assert available is True
    assert url == "https://cdn.example/mxl/a.mxl"
