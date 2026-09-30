"""Errores del resolvedor de IA. Ninguno debe tumbar el resto de storage."""

from __future__ import annotations


class AiNotConfiguredError(RuntimeError):
    """El resolvedor de IA no está configurado (`OSAP_STORAGE_GEMINI_API_KEY` ausente)."""


class AiUpstreamError(RuntimeError):
    """Gemini no respondió correctamente (timeout, 429/503 agotado, respuesta ilegible).

    La propuesta no se guarda: se propaga como 503 `AI_UNAVAILABLE` para que el panel lo
    muestre como fallo temporal y no cree una propuesta falsa.
    """
