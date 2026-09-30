"""Resolutores de atribución asistida por IA (Gemini y fake)."""

from __future__ import annotations

from infrastructure.ai.errors import AiNotConfiguredError, AiUpstreamError
from infrastructure.ai.fake_attribution_resolver import FakeAttributionResolver
from infrastructure.ai.gemini_attribution_resolver import GeminiWorkAttributionResolver
from infrastructure.ai.resolver_factory import build_attribution_resolver

__all__ = [
    "AiNotConfiguredError",
    "AiUpstreamError",
    "FakeAttributionResolver",
    "GeminiWorkAttributionResolver",
    "build_attribution_resolver",
]
