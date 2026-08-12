from __future__ import annotations

import hashlib

from domain.entities.work import Work
from domain.ports.work_repository import WorkRepository

_EXTERNAL_PREFIX = "ext:"


def external_work_key(reference: str) -> str:
    """Clave determinista de una obra externa, derivada de su referencia.

    Reutiliza `work_key` (la identidad única existente) para deduplicar: la misma
    referencia siempre produce la misma clave -> misma obra. La procedencia
    (proveedor) no forma parte de la clave, por lo que dos proveedores con la misma
    referencia resuelven a la misma obra.
    """
    digest = hashlib.sha1(reference.encode("utf-8")).hexdigest()
    return f"{_EXTERNAL_PREFIX}{digest}"


class RegisterExternalWork:
    """Registra una obra procedente de un proveedor/directorio externo sin fichero local.

    - Crea el registro en `works` si no existe (o lo recupera si ya existe).
    - Conserva la referencia externa en `relative_path`.
    - Conserva el proveedor en `tags` (procedencia, no identidad).
    - No crea fichero local, no inventa URL ni descarga nada.
    - La identidad interna sigue siendo `work_id`; la deduplicación usa `work_key`.
    """

    def __init__(self, works: WorkRepository) -> None:
        self._works = works

    async def execute(
        self,
        *,
        reference: str,
        provider: str,
        composer: str | None = None,
        title: str | None = None,
    ) -> Work:
        reference = (reference or "").strip()
        if not reference:
            raise ValueError("reference cannot be empty")
        provider = (provider or "").strip()

        work_key = external_work_key(reference)
        existing = await self._works.get_by_work_key(work_key)
        if existing is not None:
            return existing

        work = await self._works.create(
            Work(
                work_key=work_key,
                relative_path=reference,
                tags=provider,
                composer=composer,
                title=title,
            )
        )
        return work
