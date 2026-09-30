"""Resolvedor Gemini (HTTP) para la atribución asistida.

Solo propone: devuelve JSON estructurado y **nunca** escribe en la BD. La API key se lee de
entorno (`OSAP_STORAGE_GEMINI_API_KEY`) y no se persiste ni se registra.

Modelo: `OSAP_STORAGE_GEMINI_MODEL` (por defecto `gemini-flash-lite-latest`). Los modelos
flash "grandes" son más lentos e intermitentemente devuelven 503; el lite responde en ~1 s y
basta para esta tarea. `gemini-2.5-flash`/`gemini-2.5-flash-lite` ya no están disponibles para
claves nuevas (404), de ahí el cambio de valor por defecto.

Robustez: timeout de 60 s y hasta 3 intentos ante 429, 503 o `httpx.TimeoutException`, con
backoff progresivo acotado. Si se agotan, lanza `AiUpstreamError` (error controlado, 503): la
propuesta **no** se guarda, así que nunca queda una propuesta falsa.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
from domain.ports.work_attribution_ai import PROMPT_VERSION, AiProposal, WorkContext

from infrastructure.ai.errors import AiNotConfiguredError, AiUpstreamError

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-flash-lite-latest"
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BACKOFF = 1.5
_MAX_BACKOFF = 8.0
_RETRY_STATUS = frozenset({429, 503})

_INSTRUCTIONS = (
    "Eres un investigador musicológico. Dada la información de una obra musical, identifica "
    "al autor si la evidencia lo permite. Reglas estrictas:\n"
    "- No inventes personas ni obras. Si la evidencia es insuficiente, usa resolution=unknown.\n"
    "- Si la obra es anónima o tradicional, usa resolution=anonymous o traditional (no una persona).\n"
    "- Devuelve SOLO JSON válido con este esquema:\n"
    '{"resolution":"identified|anonymous|traditional|unknown","person_name":string|null,'
    '"role_name":string|null,"confidence":number|null,'
    '"evidence":[{"type":string,"text":string}],"reason":string}\n'
    "- `person_name`: nombre del autor SOLO si resolution=identified; si no, null.\n"
    "- `role_name`: normalmente 'Compositor/a' cuando identified."
)

# Esquema estricto de respuesta (además del prompt): refuerza el contrato que valida el MVP.
_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "resolution": {
            "type": "string",
            "enum": ["identified", "anonymous", "traditional", "unknown"],
        },
        "person_name": {"type": "string", "nullable": True},
        "role_name": {"type": "string", "nullable": True},
        "confidence": {"type": "number", "nullable": True},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["type", "text"],
            },
        },
        "reason": {"type": "string", "nullable": True},
    },
    "required": ["resolution"],
    "propertyOrdering": ["resolution", "person_name", "role_name", "confidence", "evidence", "reason"],
}


def _user_prompt(context: WorkContext) -> str:
    payload = {
        "work_id": context.work_id,
        "title": context.title,
        "source": context.source,
        "source_id": context.source_id,
        "catalogue": context.catalogue,
        "year": context.year,
        "opus": context.opus,
        "genre": context.genre,
        "instrumentation": context.instrumentation,
        "attr_type": context.attr_type,
        "attribution_note": context.attribution_note,
        "existing_persons": context.existing_persons,
    }
    return "Datos de la obra (JSON):\n" + json.dumps(payload, ensure_ascii=False)


class GeminiWorkAttributionResolver:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        backoff: float = _DEFAULT_BACKOFF,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("OSAP_STORAGE_GEMINI_API_KEY", "")
        self.model = model or os.environ.get("OSAP_STORAGE_GEMINI_MODEL") or _DEFAULT_MODEL
        self._timeout = timeout
        self._max_attempts = max(1, max_attempts)
        self._backoff = max(0.0, backoff)
        self._transport = transport

    async def propose(self, context: WorkContext) -> AiProposal:
        if not self._api_key:
            raise AiNotConfiguredError("OSAP_STORAGE_GEMINI_API_KEY no configurada")
        body = {
            "systemInstruction": {"parts": [{"text": _INSTRUCTIONS}]},
            "contents": [{"role": "user", "parts": [{"text": _user_prompt(context)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
                "temperature": 0.0,
            },
        }
        url = f"{_API_BASE}/{self.model}:generateContent"

        last_error = ""
        for attempt in range(1, self._max_attempts + 1):
            try:
                data = await self._request_json(url, body)
            except httpx.TimeoutException as exc:
                last_error = f"timeout ({type(exc).__name__})"
            except _RetryableStatus as exc:
                last_error = str(exc)
            else:
                return self._to_proposal(data)
            if attempt < self._max_attempts:
                await asyncio.sleep(min(self._backoff * 2 ** (attempt - 1), _MAX_BACKOFF))

        raise AiUpstreamError(
            f"Gemini no disponible tras {self._max_attempts} intentos ({self.model}): {last_error}"
        )

    async def _request_json(self, url: str, body: dict[str, object]) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(url, params={"key": self._api_key}, json=body)
        if response.status_code in _RETRY_STATUS:
            raise _RetryableStatus(f"HTTP {response.status_code}: {_brief(response.text)}")
        if response.status_code >= 400:
            # 400/401/403/404: no se reintenta (clave, modelo o petición mal formada).
            raise AiUpstreamError(f"Gemini HTTP {response.status_code}: {_brief(response.text)}")
        return response.json()

    def _to_proposal(self, data: dict[str, object]) -> AiProposal:
        try:
            candidates = data["candidates"]  # type: ignore[index]
            text = candidates[0]["content"]["parts"][0]["text"]  # type: ignore[index,union-attr]
            parsed = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AiUpstreamError(f"respuesta de Gemini no parseable: {type(exc).__name__}") from exc
        if not isinstance(parsed, dict):
            raise AiUpstreamError("respuesta de Gemini no es un objeto JSON")

        resolution = str(parsed.get("resolution") or "unknown")
        if resolution not in ("identified", "anonymous", "traditional", "unknown"):
            resolution = "unknown"
        person = parsed.get("person_name")
        role = parsed.get("role_name")
        confidence = parsed.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None  # type: ignore[arg-type]
        except (TypeError, ValueError):
            confidence_value = None
        evidence = parsed.get("evidence")
        return AiProposal(
            resolution=resolution,  # type: ignore[arg-type]
            person_name=str(person) if person else None,
            role_name=str(role) if role else None,
            confidence=confidence_value,
            evidence=evidence if isinstance(evidence, list) else [],
            reason=str(parsed.get("reason") or "") or None,
            raw={"parsed": parsed, "model": self.model, "prompt_version": PROMPT_VERSION},
        )


class _RetryableStatus(RuntimeError):
    """Estado transitorio de Gemini (429/503) que merece reintento."""


def _brief(text: str) -> str:
    return " ".join(text.split())[:200]
