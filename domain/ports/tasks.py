from __future__ import annotations

from collections.abc import Coroutine
from typing import Any, Protocol


class TaskScheduler(Protocol):
    """Ejecuta trabajo asíncrono en segundo plano."""

    def schedule(self, coro: Coroutine[Any, Any, Any]) -> None: ...
