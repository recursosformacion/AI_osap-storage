from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from application.use_cases.export_file import ExportFile
from application.use_cases.stream_file import FileStream
from domain.entities.file import File
from domain.exceptions import ExportFormatUnavailable
from domain.services.score_export import (
    ExportFormat,
    parse_export_format,
    source_format,
    supports,
)
from infrastructure.score.cache import ExportCache


class _FakeFiles:
    def __init__(self, file: File) -> None:
        self._file = file

    async def get_by_id(self, file_id: int) -> File | None:
        return self._file if file_id == self._file.id else None


class _FakeStream:
    def __init__(self, content: bytes) -> None:
        self.calls = 0
        self._content = content

    async def execute(self, file_id: int, provider_id: int | None = None) -> FileStream:
        self.calls += 1
        async def chunks() -> AsyncIterator[bytes]:
            yield self._content

        return FileStream(
            file=File(sha256="a" * 64, name="source.ly", id=file_id),
            provider=object(),  # type: ignore[arg-type]
            location=object(),  # type: ignore[arg-type]
            content=chunks(),
            friendly_name="source.ly",
        )


class _FakeConverter:
    def __init__(self) -> None:
        self.calls = 0

    def convert(
        self, source: Path, source_format: ExportFormat, target: ExportFormat, output_dir: Path
    ) -> Path:
        self.calls += 1
        output = output_dir / "score.pdf"
        output.write_bytes(b"%PDF-fake")
        return output


def test_format_detection_and_capabilities() -> None:
    assert source_format("piece.ly") == ExportFormat.LY
    assert source_format("piece.mxl") == ExportFormat.MXL
    assert source_format("piece.musicxml") == ExportFormat.MUSICXML
    assert source_format("piece.pdf") == ExportFormat.PDF
    assert supports(ExportFormat.LY, ExportFormat.PDF)
    assert not supports(ExportFormat.LY, ExportFormat.MXL)
    assert parse_export_format("lilypond") == ExportFormat.LY


async def test_export_uses_cache_and_does_not_store_derivatives(tmp_path: Path) -> None:
    file = File(sha256="b" * 64, name="piece.ly", id=7)
    stream = _FakeStream(b"\\version \\\"2.24.0\\\"")
    converter = _FakeConverter()
    cache = ExportCache(tmp_path / "cache", ttl_seconds=3600)
    use_case = ExportFile(_FakeFiles(file), stream, converter, cache)  # type: ignore[arg-type]

    first = await use_case.execute(7, ExportFormat.PDF)
    second = await use_case.execute(7, ExportFormat.PDF)

    assert first.path.exists()
    assert first.path == second.path
    assert first.media_type == "application/pdf"
    assert converter.calls == 1
    assert stream.calls == 1


async def test_lilypond_to_mxl_is_not_supported(tmp_path: Path) -> None:
    file = File(sha256="c" * 64, name="piece.ly", id=8)
    use_case = ExportFile(
        _FakeFiles(file),  # type: ignore[arg-type]
        _FakeStream(b""),
        _FakeConverter(),
        ExportCache(tmp_path / "cache"),
    )
    with pytest.raises(ExportFormatUnavailable):
        await use_case.execute(8, ExportFormat.MXL)
