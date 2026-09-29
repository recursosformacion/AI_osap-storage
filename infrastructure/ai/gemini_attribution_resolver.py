"""Resolvedor Gemini (HTTP) para la atribución asistida.

Solo propone: devuelve JSON estructurado. No crea personas ni escribe en la BD.
La API key se lee de entorno (`OSAP_STORAGE_GEMINI_API_KEY`) y **nunca** se persiste ni
se registra. El modelo es configurable (`OSAP_STORAGE_GEMINI_MODEL`).
"""

from __future__ import annotations

import json
import os

import httpx
from domain.ports.work_attribution_ai import PROMPT_VERSION, AiProposal, WorkContext

from infrastructure.ai.errors import AiNotConfiguredError

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

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
    def __init__(self, *, api_key: str | None = None, model: str | None = None, timeout: float = 30.0) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("OSAP_STORAGE_GEMINI_API_KEY", "")
        self.model = model or os.environ.get("OSAP_STORAGE_GEMINI_MODEL", "gemini-2.5-flash")
        self._timeout = timeout

    async def propose(self, context: WorkContext) -> AiProposal:
        if not self._api_key:
            raise AiNotConfiguredError("OSAP_STORAGE_GEMINI_API_KEY no configurada")
        body = {
            "systemInstruction": {"parts": [{"text": _INSTRUCTIONS}]},
            "contents": [{"role": "user", "parts": [{"text": _user_prompt(context)}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0},
        }
        url = f"{_API_BASE}/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, params={"key": self._api_key}, json=body)
            response.raise_for_status()
            data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        resolution = str(parsed.get("resolution") or "unknown")
        if resolution not in ("identified", "anonymous", "traditional", "unknown"):
            resolution = "unknown"
        person = parsed.get("person_name")
        role = parsed.get("role_name")
        confidence = parsed.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
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
