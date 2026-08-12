from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities.composer import UNKNOWN_COMPOSER_ID
from domain.entities.work import Work
from domain.ports.work_repository import WorkRepository
from domain.services.composer_resolver import ComposerResolver


@dataclass(frozen=True)
class WorkEnrichment:
    composer: str | None = None
    title: str | None = None
    subtitle: str | None = None
    artist: str | None = None
    song_name: str | None = None
    catalogue: str | None = None
    musical_key: str | None = None
    duration: str | None = None
    measures: int | None = None
    pages: int | None = None
    parts: int | None = None
    complexity: int | None = None
    license: str | None = None
    public_domain: bool = False
    description: str | None = None
    thumbnails: str | None = None
    tags: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    parts_names: list[str] = field(default_factory=list)


class EnrichWork:
    """Aplica el enriquecimiento a una Work (metadata + tablas auxiliares). Idempotente."""

    def __init__(self, works: WorkRepository, resolver: ComposerResolver | None = None) -> None:
        self._works = works
        self._resolver = resolver

    async def execute(self, work: Work, e: WorkEnrichment) -> None:
        if work.id is None:
            return
        work.composer = e.composer or work.composer
        work.title = e.title or work.title
        work.subtitle = e.subtitle or work.subtitle
        work.artist = e.artist or work.artist
        work.song_name = e.song_name or work.song_name
        work.catalogue = e.catalogue or work.catalogue
        work.musical_key = e.musical_key or work.musical_key
        work.duration = e.duration or work.duration
        work.measures = e.measures if e.measures is not None else work.measures
        work.pages = e.pages if e.pages is not None else work.pages
        work.parts = e.parts if e.parts is not None else work.parts
        work.complexity = e.complexity if e.complexity is not None else work.complexity
        work.license = e.license or work.license
        if e.public_domain:
            work.public_domain = True
        work.description = e.description or work.description
        work.thumbnails = e.thumbnails or work.thumbnails
        if e.genres:
            work.genre = e.genres[0]
        if e.tags:
            work.tags = ", ".join(e.tags)
        if e.instruments:
            work.instrumentation = ", ".join(e.instruments)
        elif e.parts_names:
            work.instrumentation = ", ".join(e.parts_names)

        if self._resolver is not None:
            from domain.services.composer_quality import extract_composer_name

            extracted = extract_composer_name(work.composer)
            resolved = await self._resolver.resolve(extracted) if extracted else None
            work.composer_id = resolved[0] if resolved else UNKNOWN_COMPOSER_ID

        await self._works.update(work)
        await self._works.replace_tags(work.id, e.tags)
        await self._works.replace_genres(work.id, e.genres)
        await self._works.replace_instruments(work.id, e.instruments)
        await self._works.replace_parts(work.id, e.parts_names)
