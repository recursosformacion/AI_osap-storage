"""Cliente mínimo para APIs compatibles con OpenAI (Groq, Mistral, OpenRouter).

Las claves se leen del entorno; nunca del código.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", ""),
}
RETRY = {429, 500, 502, 503, 504}


def provider_key(provider: str) -> str:
    env = {
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }[provider]
    return os.environ.get(env, "").strip()


def default_model(provider: str) -> str:
    return PROVIDERS[provider][1]


def call_json(
    provider: str,
    model: str,
    system_prompt: str,
    user_content: str,
    *,
    api_key: str | None = None,
    timeout: int = 300,
) -> list[dict[str, Any]]:
    """Devuelve la lista `results` de una respuesta JSON del modelo."""
    if provider not in PROVIDERS:
        raise RuntimeError(f"proveedor no soportado: {provider}")
    key = api_key or provider_key(provider)
    if not key:
        raise RuntimeError(f"falta la clave de {provider}")
    url, default = PROVIDERS[provider]
    model = model or default
    if not model:
        raise RuntimeError("falta --model para este proveedor")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "OSAP-Catalog/1.0"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://app.openmusicrepository.com"
        headers["X-Title"] = "OSAP catalog enrichment"
    last = ""
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            content = str(data.get("choices", [{}])[0].get("message", {}).get("content") or "")
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
            if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
                parsed = parsed["results"]
            if not isinstance(parsed, list):
                raise RuntimeError("respuesta sin array results")
            return [x for x in parsed if isinstance(x, dict)]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:400]
            last = f"HTTP {exc.code}: {body}"
            if exc.code not in RETRY:
                raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"{provider} no disponible: {last}")
