from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from domain.exceptions import ExportFormatUnavailable


class ExportFormat(StrEnum):
    ORIGINAL = "original"
    MXL = "mxl"
    MUSICXML = "musicxml"
    LY = "ly"
    PDF = "pdf"
    MIDI = "midi"
    SVG = "svg"


_FORMAT_ALIASES: dict[str, ExportFormat] = {
    "original": ExportFormat.ORIGINAL,
    "source": ExportFormat.ORIGINAL,
    "mxl": ExportFormat.MXL,
    "musicxml": ExportFormat.MUSICXML,
    "xml": ExportFormat.MUSICXML,
    "ly": ExportFormat.LY,
    "lilypond": ExportFormat.LY,
    "pdf": ExportFormat.PDF,
    "midi": ExportFormat.MIDI,
    "mid": ExportFormat.MIDI,
    "svg": ExportFormat.SVG,
}

_MEDIA_TYPES: dict[ExportFormat, str] = {
    ExportFormat.MXL: "application/vnd.recordare.musicxml",
    ExportFormat.MUSICXML: "application/vnd.recordare.musicxml+xml",
    ExportFormat.LY: "text/x-lilypond",
    ExportFormat.PDF: "application/pdf",
    ExportFormat.MIDI: "audio/midi",
    ExportFormat.SVG: "image/svg+xml",
}


def parse_export_format(value: str | None) -> ExportFormat:
    if not value:
        return ExportFormat.ORIGINAL
    fmt = _FORMAT_ALIASES.get(value.strip().lower())
    if fmt is None:
        raise ExportFormatUnavailable(f"formato de salida desconocido: {value}")
    return fmt


def media_type_for(fmt: ExportFormat, fallback: str | None = None) -> str:
    return _MEDIA_TYPES.get(fmt) or fallback or "application/octet-stream"


def source_format(name: str, mime_type: str | None = None) -> ExportFormat | None:
    """Formato del original a partir de la extensión y, si falta, del MIME."""
    suffix = Path(name or "").suffix.lower()
    by_suffix = {
        ".mxl": ExportFormat.MXL,
        ".musicxml": ExportFormat.MUSICXML,
        ".xml": ExportFormat.MUSICXML,
        ".ly": ExportFormat.LY,
        ".lyi": ExportFormat.LY,
        ".pdf": ExportFormat.PDF,
        ".mid": ExportFormat.MIDI,
        ".midi": ExportFormat.MIDI,
        ".svg": ExportFormat.SVG,
    }
    if suffix in by_suffix:
        return by_suffix[suffix]
    mime = (mime_type or "").lower()
    if "musicxml" in mime or "recordare" in mime:
        return ExportFormat.MUSICXML
    if "lilypond" in mime:
        return ExportFormat.LY
    if mime == "application/pdf":
        return ExportFormat.PDF
    if "midi" in mime:
        return ExportFormat.MIDI
    return None


_SUPPORTED: dict[ExportFormat, set[ExportFormat]] = {
    ExportFormat.MXL: {ExportFormat.MXL, ExportFormat.LY, ExportFormat.PDF, ExportFormat.MIDI, ExportFormat.SVG},
    ExportFormat.MUSICXML: {
        ExportFormat.MUSICXML,
        ExportFormat.LY,
        ExportFormat.PDF,
        ExportFormat.MIDI,
        ExportFormat.SVG,
    },
    ExportFormat.LY: {ExportFormat.LY, ExportFormat.PDF, ExportFormat.MIDI, ExportFormat.SVG},
    ExportFormat.PDF: {ExportFormat.PDF},
    ExportFormat.MIDI: {ExportFormat.MIDI},
    ExportFormat.SVG: {ExportFormat.SVG},
}


def supports(source: ExportFormat | None, target: ExportFormat) -> bool:
    if target == ExportFormat.ORIGINAL:
        return source is not None
    if source is None:
        return False
    return target in _SUPPORTED.get(source, set())


def available_formats(source: ExportFormat | None) -> list[ExportFormat]:
    if source is None:
        return [ExportFormat.ORIGINAL]
    return [fmt for fmt in ExportFormat if supports(source, fmt)]


@dataclass(frozen=True)
class ExportArtifact:
    path: Path
    format: ExportFormat
    filename: str
    media_type: str


class ScoreConverter(Protocol):
    def convert(self, source: Path, source_format: ExportFormat, target: ExportFormat, output_dir: Path) -> Path:
        """Genera un derivado efímero; el llamador decide cuándo borrarlo."""
