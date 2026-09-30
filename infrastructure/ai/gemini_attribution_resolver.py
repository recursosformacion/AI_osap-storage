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

Cuota: `OSAP_STORAGE_GEMINI_API_KEY` admite **varias claves** separadas por comas (p. ej.
`clave1,clave2,clave3`); cada intento rota a la siguiente clave, de modo que la cuota se reparte
entre proyectos si un proveedor limita por clave.
"""

from __future__ import annotations

import asyncio
import json
import os
import re

import httpx
from domain.ports.work_attribution_ai import (
    AI_ROLE_KEYS,
    PROMPT_VERSION,
    AiProposal,
    AiRelation,
    WorkContext,
)

from infrastructure.ai.errors import AiNotConfiguredError, AiUpstreamError

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-flash-lite-latest"
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BACKOFF = 1.5
_MAX_BACKOFF = 8.0
_RETRY_STATUS = frozenset({429, 503})


def parse_api_keys(value: str | None) -> list[str]:
    """Una o varias claves separadas por comas, punto y coma o espacios.

    Permite repartir la cuota cuando un proyecto tiene varias claves (`key1,key2,key3`).
    Nunca se registra el valor de las claves.
    """
    if not value:
        return []
    return [part for part in re.split(r"[,;\s]+", value.strip()) if part]

_INSTRUCTIONS = (
    "Eres un investigador musicológico. Dada la información de una obra musical, identifica "
    "su atribución y las personas relacionadas si la evidencia lo permite. Reglas estrictas:\n"
    "- No inventes personas ni obras. Si no puedes identificar una relación con evidencia, omítela.\n"
    "- Dos capas INDEPENDIENTES:\n"
    "  * `resolution`: atribución de la OBRA: identified | anonymous | traditional | unknown.\n"
    "    Si es anónima o tradicional usa esos valores (no una persona).\n"
    "  * `relations`: PERSONAS relacionadas con su rol. OJO: una obra anonymous o traditional "
    "puede tener arreglista, adaptador, transcriptor o letrista identificable; si lo conoces, "
    "ponlo en `relations` aunque `resolution` sea anonymous o traditional.\n"
    "- `relations[].role_key` SOLO puede ser uno de: " + ", ".join(AI_ROLE_KEYS) + ".\n"
    "- Si el título y el catálogo no concuerdan, no los fuerces: anótalo en `contradictions` y "
    "baja la confianza (o usa resolution=unknown si no puedes decidir).\n"
    "- Devuelve SOLO JSON válido con este esquema:\n"
    '{"resolution":"identified|anonymous|traditional|unknown","person_name":string|null,'
    '"role_name":string|null,"confidence":number|null,'
    '"evidence":[{"type":string,"text":string}],'
    '"relations":[{"person_name":string,"role_key":string,"confidence":number|null,'
    '"evidence":[{"type":string,"text":string}],"reason":string|null}],'
    '"contradictions":[string],"reason":string}\n'
    "- `person_name`: nombre del compositor SOLO si resolution=identified; si no, null.\n"
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
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "person_name": {"type": "string"},
                    "role_key": {"type": "string", "enum": list(AI_ROLE_KEYS)},
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
                "required": ["person_name", "role_key"],
            },
        },
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string", "nullable": True},
    },
    "required": ["resolution"],
    "propertyOrdering": [
        "resolution", "person_name", "role_name", "confidence", "evidence",
        "relations", "contradictions", "reason",
    ],
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
        "existing_relations": context.existing_relations,
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
        raw_keys = api_key if api_key is not None else os.environ.get("OSAP_STORAGE_GEMINI_API_KEY", "")
        self._api_keys = parse_api_keys(raw_keys)
        self.model = model or os.environ.get("OSAP_STORAGE_GEMINI_MODEL") or _DEFAULT_MODEL
        self._timeout = timeout
        self._max_attempts = max(1, max_attempts)
        self._backoff = max(0.0, backoff)
        self._transport = transport

    @property
    def key_count(self) -> int:
        """Número de claves configuradas (sin exponer su valor)."""
        return len(self._api_keys)

    async def propose(self, context: WorkContext) -> AiProposal:
        if not self._api_keys:
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
            # Rotación de claves: cada intento usa la siguiente (reparte la cuota/proyecto).
            key = self._api_keys[(attempt - 1) % len(self._api_keys)]
            try:
                data = await self._request_json(url, body, key)
            except httpx.TimeoutException as exc:
                last_error = f"timeout ({type(exc).__name__})"
            except _RetryableStatus as exc:
                last_error = str(exc)
            else:
                return self._to_proposal(data)
            if attempt < self._max_attempts:
                await asyncio.sleep(min(self._backoff * 2 ** (attempt - 1), _MAX_BACKOFF))

        raise AiUpstreamError(
            f"Gemini no disponible tras {self._max_attempts} intentos ({self.model}, "
            f"{self.key_count} clave(s)): {last_error}"
        )

    async def _request_json(self, url: str, body: dict[str, object], key: str) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(url, params={"key": key}, json=body)
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
            relations=_parse_relations(parsed.get("relations")),
            contradictions=_parse_contradictions(parsed.get("contradictions")),
            raw={"parsed": parsed, "model": self.model, "prompt_version": PROMPT_VERSION},
        )


class _RetryableStatus(RuntimeError):
    """Estado transitorio de Gemini (429/503) que merece reintento."""


def _as_confidence(value: object) -> float | None:
    try:
        return float(value) if value is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_relations(raw: object) -> list[AiRelation]:
    """Personas propuestas: se descartan las que traen un `role_key` fuera del catálogo."""
    if not isinstance(raw, list):
        return []
    relations: list[AiRelation] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        person = str(item.get("person_name") or "").strip()
        role = str(item.get("role_key") or "").strip().lower()
        if not person or role not in AI_ROLE_KEYS or (person.lower(), role) in seen:
            continue
        seen.add((person.lower(), role))
        evidence = item.get("evidence")
        relations.append(
            AiRelation(
                person_name=person,
                role_key=role,
                confidence=_as_confidence(item.get("confidence")),
                evidence=evidence if isinstance(evidence, list) else [],
                reason=str(item.get("reason") or "") or None,
            )
        )
    return relations


def _parse_contradictions(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and text not in out:
            out.append(text[:500])
    return out[:10]


def _brief(text: str) -> str:
    return " ".join(text.split())[:200]
