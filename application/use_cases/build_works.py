from __future__ import annotations

import os
from dataclasses import dataclass

from domain.entities.composer import UNKNOWN_COMPOSER_ID
from domain.entities.work import Work
from domain.ports.archive_repositories import ArchiveEntryRepository
from domain.ports.work_repository import WorkRepository
from domain.services.composer_resolver import ComposerResolver


def work_key_of(relative_path: str) -> str:
    """Clave de agrupación de la obra: el hash PDMX (nombre base sin extensión).

    mxl/pdf/mid de la misma canción comparten ese hash.
    """
    name = os.path.basename(relative_path)
    return os.path.splitext(name)[0]


@dataclass(frozen=True)
class BuildWorksResult:
    works: int
    linked: int


class BuildWorks:
    """Crea una Work por cada recurso (hash PDMX) y enlaza los ArchiveEntry.

    Idempotente: ignora entradas que ya tienen work_id.
    """

    def __init__(
        self,
        entries: ArchiveEntryRepository,
        works: WorkRepository,
        resolver: ComposerResolver | None = None,
    ) -> None:
        self._entries = entries
        self._works = works
        self._resolver = resolver

    async def execute(self) -> BuildWorksResult:
        cache: dict[str, int] = {}
        composer_cache: dict[str, str | None] = {}
        works_created = 0
        linked = 0
        limit = 1000
        offset = 0

        async def composer_id_of(name: str | None) -> str | None:
            from domain.services.composer_quality import extract_composer_name

            extracted = extract_composer_name(name)
            if extracted is None:
                return UNKNOWN_COMPOSER_ID
            if extracted not in composer_cache:
                resolved = await self._resolver.resolve(extracted) if self._resolver else None
                composer_cache[extracted] = resolved[0] if resolved else UNKNOWN_COMPOSER_ID
            return composer_cache[extracted]

        while True:
            batch = await self._entries.list_all(limit=limit, offset=offset)
            if not batch:
                break
            pending = [e for e in batch if e.work_id is None]
            for entry in pending:
                key = work_key_of(entry.relative_path)
                work_id = cache.get(key)
                if work_id is None:
                    work = await self._works.get_by_work_key(key)
                    if work is None:
                        work = await self._works.create(
                            Work(
                                work_key=key,
                                composer=entry.composer,
                                composer_id=await composer_id_of(entry.composer),
                                title=entry.title,
                            )
                        )
                        works_created += 1
                    assert work.id is not None
                    cache[key] = work.id
                    work_id = work.id
                entry.work_id = work_id
            if pending:
                await self._entries.bulk_update_work_ids(pending)
                linked += len(pending)
            offset += limit

        return BuildWorksResult(works=works_created, linked=linked)
