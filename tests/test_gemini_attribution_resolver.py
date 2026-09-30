"""Tests del resolvedor Gemini: modelo por defecto, esquema JSON, reintentos y errores.

Se usa `httpx.MockTransport` (sin red) y `backoff=0` para que los reintentos sean inmediatos.
No se guarda ninguna propuesta si la IA falla: eso lo cubre el test de caso de uso.
"""

from __future__ import annotations

import json

import httpx
import pytest
from domain.ports.work_attribution_ai import WorkContext
from infrastructure.ai.errors import AiNotConfiguredError, AiUpstreamError
from infrastructure.ai.gemini_attribution_resolver import GeminiWorkAttributionResolver

_OK_BODY = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "resolution": "identified",
                                "person_name": "Louise Farrenc",
                                "role_name": "Compositor/a",
                                "confidence": 0.91,
                                "evidence": [{"type": "source_metadata", "text": "PDMX"}],
                                "reason": "atribución documentada",
                            }
                        )
                    }
                ]
            }
        }
    ]
}


def _context() -> WorkContext:
    return WorkContext(work_id=3, title="Helvic Head", catalogue="Op. 67", genre="Canción")


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


def _resolver(handler, **kwargs) -> GeminiWorkAttributionResolver:  # type: ignore[no-untyped-def]
    return GeminiWorkAttributionResolver(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        backoff=0.0,
        **kwargs,
    )


async def test_exito_sin_reintento() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_OK_BODY)

    proposal = await _resolver(handler).propose(_context())

    assert calls == 1
    assert proposal.resolution == "identified"
    assert proposal.person_name == "Louise Farrenc"
    assert proposal.confidence == pytest.approx(0.91)
    assert proposal.evidence == [{"type": "source_metadata", "text": "PDMX"}]


async def test_la_peticion_lleva_esquema_y_modelo_por_defecto() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = _body(request)
        return httpx.Response(200, json=_OK_BODY)

    resolver = _resolver(handler)
    await resolver.propose(_context())

    assert resolver.model == "gemini-flash-lite-latest"
    assert "gemini-flash-lite-latest:generateContent" in seen["url"]
    config = seen["body"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    schema = config["responseSchema"]
    assert schema["required"] == ["resolution"]
    assert schema["properties"]["resolution"]["enum"] == [
        "identified",
        "anonymous",
        "traditional",
        "unknown",
    ]
    assert "person_name" in schema["properties"]


@pytest.mark.parametrize("retry_status", [503, 429])
async def test_reintenta_ante_503_y_429(retry_status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(retry_status, json={"error": {"message": "transitorio"}})
        return httpx.Response(200, json=_OK_BODY)

    proposal = await _resolver(handler).propose(_context())

    assert calls == 2
    assert proposal.resolution == "identified"


async def test_reintenta_ante_timeout() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("timeout de lectura")
        return httpx.Response(200, json=_OK_BODY)

    proposal = await _resolver(handler).propose(_context())

    assert calls == 2
    assert proposal.person_name == "Louise Farrenc"


async def test_agotamiento_de_reintentos_lanza_error_controlado() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": "high demand"}})

    with pytest.raises(AiUpstreamError) as excinfo:
        await _resolver(handler, max_attempts=3).propose(_context())

    assert calls == 3
    assert "3 intentos" in str(excinfo.value)


async def test_error_definitivo_no_se_reintenta() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "API key not valid"}})

    with pytest.raises(AiUpstreamError):
        await _resolver(handler).propose(_context())

    assert calls == 1


async def test_json_no_conforme_lanza_error_controlado() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "no-json"}]}}]})

    with pytest.raises(AiUpstreamError):
        await _resolver(handler).propose(_context())


async def test_resolucion_fuera_del_enum_se_normaliza_a_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"resolution": "inventada"})}]}}]}
        return httpx.Response(200, json=body)

    proposal = await _resolver(handler).propose(_context())

    assert proposal.resolution == "unknown"
    assert proposal.person_name is None


async def test_sin_key_no_llama_a_gemini() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_OK_BODY)

    resolver = GeminiWorkAttributionResolver(api_key="", transport=httpx.MockTransport(handler), backoff=0.0)
    with pytest.raises(AiNotConfiguredError):
        await resolver.propose(_context())

    assert calls == 0
