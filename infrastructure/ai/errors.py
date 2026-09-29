"""Error de IA no configurada (sin API key). Nunca rompe el resto de storage."""

from __future__ import annotations


class AiNotConfiguredError(RuntimeError):
    """El resolvedor de IA no está configurado (`OSAP_STORAGE_GEMINI_API_KEY` ausente)."""
