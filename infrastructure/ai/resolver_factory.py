"""Selección del resolvedor de IA según entorno (sin exponer la clave)."""

from __future__ import annotations

import os

from domain.ports.work_attribution_ai import AiProposal, WorkContext

from infrastructure.ai.errors import AiNotConfiguredError
from infrastructure.ai.fake_attribution_resolver import FakeAttributionResolver
from infrastructure.ai.gemini_attribution_resolver import GeminiWorkAttributionResolver


class NullAttributionResolver:
    """Sin clave: `propose` falla con un error claro; el resto de storage no se ve afectado."""

    model = "unconfigured"

    async def propose(self, context: WorkContext) -> AiProposal:
        raise AiNotConfiguredError("IA no configurada: falta OSAP_STORAGE_GEMINI_API_KEY")


def build_attribution_resolver() -> (
    GeminiWorkAttributionResolver | FakeAttributionResolver | NullAttributionResolver
):
    """`OSAP_STORAGE_AI_RESOLVER=fake` fuerza el fake; si no, Gemini, y si no hay clave, Null."""
    if os.environ.get("OSAP_STORAGE_AI_RESOLVER", "").strip().lower() == "fake":
        return FakeAttributionResolver()
    if os.environ.get("OSAP_STORAGE_GEMINI_API_KEY", "").strip():
        return GeminiWorkAttributionResolver()
    return NullAttributionResolver()
