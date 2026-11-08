from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from domain.entities.file import File
from domain.exceptions import ExportFormatUnavailable
from domain.ports.repositories import FileRepository
from domain.services.score_export import (
    ExportArtifact,
    ExportFormat,
    ScoreConverter,
    media_type_for,
    source_format,
    supports,
)
from infrastructure.score.cache import ExportCache

from application.use_cases.stream_file import StreamFile


class ExportFile:
    """Genera un derivado efímero para una descarga concreta.

    El artefacto se cachea en disco con TTL, pero no se registra como recurso ni
    representación. Si la caché falla o se limpia, se regenera desde el original.
    """

    def __init__(
        self,
        files: FileRepository,
        stream_file: StreamFile,
        converter: ScoreConverter,
        cache: ExportCache,
    ) -> None:
        self._files = files
        self._stream_file = stream_file
        self._converter = converter
        self._cache = cache

    async def execute(
        self, file_id: int, target: ExportFormat, provider_id: int | None = None
    ) -> ExportArtifact:
        file = await self._files.get_by_id(file_id)
        if file is None:
            from domain.exceptions import EntityNotFound

            raise EntityNotFound("file", file_id)
        source = source_format(file.name, file.mime_type)
        if target == ExportFormat.ORIGINAL:
            raise ExportFormatUnavailable("usa /content para el original")
        if not supports(source, target):
            raise ExportFormatUnavailable(
                f"no hay conversión de {source.value if source else 'desconocido'} a {target.value}"
            )
        assert source is not None
        key = self._cache.key(file, source, target)
        cached = self._cache.get(key, target)
        if cached is not None:
            return self._artifact(file, cached, target)

        stream = await self._stream_file.execute(file_id, provider_id)
        suffix = Path(stream.file.name or "").suffix or {
            ExportFormat.MXL: ".mxl",
            ExportFormat.MUSICXML: ".musicxml",
            ExportFormat.LY: ".ly",
            ExportFormat.PDF: ".pdf",
            ExportFormat.MIDI: ".midi",
            ExportFormat.SVG: ".svg",
        }.get(source, ".bin")
        with tempfile.TemporaryDirectory(prefix="score-export-", dir=self._cache.root) as tmp:
            workdir = Path(tmp)
            source_path = workdir / f"source{suffix}"
            with source_path.open("wb") as handle:
                async for chunk in stream.content:
                    handle.write(chunk)
            generated = await asyncio.to_thread(
                self._converter.convert, source_path, source, target, workdir
            )
            destination = self._cache.path(key, target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(generated, destination)
        self._cache.cleanup()
        return self._artifact(file, destination, target)

    @staticmethod
    def _artifact(file: File, path: Path, target: ExportFormat) -> ExportArtifact:
        suffix = {
            ExportFormat.MXL: ".mxl",
            ExportFormat.MUSICXML: ".musicxml",
            ExportFormat.LY: ".ly",
            ExportFormat.PDF: ".pdf",
            ExportFormat.MIDI: ".midi",
            ExportFormat.SVG: ".svg",
        }[target]
        stem = Path(file.name or "score").stem or "score"
        return ExportArtifact(
            path=path,
            format=target,
            filename=f"{stem}{suffix}",
            media_type=media_type_for(target, file.mime_type),
        )
