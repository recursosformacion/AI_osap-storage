from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


class AsyncioTaskScheduler:
    """Programa corrutinas como tareas asíncronas manteniendo una referencia fuerte."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def schedule(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
