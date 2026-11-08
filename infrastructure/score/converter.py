from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from domain.exceptions import ExportConversionFailed, ExportFormatUnavailable, ExportToolUnavailable
from domain.services.score_export import ExportFormat, ScoreConverter

_OUTPUT_SUFFIX = {
    ExportFormat.LY: ".ly",
    ExportFormat.PDF: ".pdf",
    ExportFormat.MIDI: ".midi",
    ExportFormat.SVG: ".svg",
}


class ExternalScoreConverter(ScoreConverter):
    """Conversores externos, sin shell y con timeout.

    La ejecución en producción debe hacerse en un worker aislado: LilyPond puede
    ejecutar Scheme y leer ficheros. Este adaptador evita el shell, pero el aislamiento
    de procesos/red corresponde al servicio que lo despliegue.
    """

    def __init__(
        self,
        *,
        lilypond_bin: str = "lilypond",
        musicxml2ly_bin: str = "musicxml2ly",
        timeout_seconds: int = 60,
    ) -> None:
        self._lilypond = lilypond_bin
        self._musicxml2ly = musicxml2ly_bin
        self._timeout = timeout_seconds

    def convert(
        self, source: Path, source_format: ExportFormat, target: ExportFormat, output_dir: Path
    ) -> Path:
        if target == source_format:
            return source
        if source_format == ExportFormat.LY:
            return self._from_lilypond(source, target, output_dir)
        if source_format in (ExportFormat.MXL, ExportFormat.MUSICXML):
            return self._from_musicxml(source, target, output_dir)
        raise ExportFormatUnavailable(
            f"no se puede convertir {source_format.value} a {target.value}"
        )

    def _from_lilypond(self, source: Path, target: ExportFormat, output_dir: Path) -> Path:
        if target not in (ExportFormat.PDF, ExportFormat.MIDI, ExportFormat.SVG):
            raise ExportFormatUnavailable(f"LilyPond no puede generar {target.value}")
        base = output_dir / "score"
        args = [self._binary(self._lilypond, "lilypond"), "-dno-point-and-click"]
        if target == ExportFormat.PDF:
            args.append("--pdf")
        elif target == ExportFormat.MIDI:
            args.append("--midi")
        elif target == ExportFormat.SVG:
            args.extend(["-dbackend=svg"])
        args.extend(["-o", str(base), str(source)])
        self._run(args, output_dir)
        return self._find_output(base, target)

    def _from_musicxml(self, source: Path, target: ExportFormat, output_dir: Path) -> Path:
        if target == ExportFormat.LY:
            output = output_dir / "score.ly"
            self._run(
                [self._binary(self._musicxml2ly, "musicxml2ly"), "-o", str(output), str(source)],
                output_dir,
            )
            if not output.exists() or output.stat().st_size == 0:
                raise ExportConversionFailed("musicxml2ly no produjo un .ly")
            return output
        if target in (ExportFormat.PDF, ExportFormat.MIDI, ExportFormat.SVG):
            ly = self._from_musicxml(source, ExportFormat.LY, output_dir)
            return self._from_lilypond(ly, target, output_dir)
        raise ExportFormatUnavailable(f"MusicXML no puede generar {target.value}")

    @staticmethod
    def _binary(configured: str, name: str) -> str:
        path = shutil.which(configured)
        if path is None:
            raise ExportToolUnavailable(f"conversor no instalado: {name} ({configured})")
        return path

    def _run(self, args: list[str], output_dir: Path) -> None:
        try:
            completed = subprocess.run(
                args,
                cwd=output_dir,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
                env={**os.environ, "HOME": str(output_dir)},
            )
        except subprocess.TimeoutExpired as exc:
            raise ExportConversionFailed(f"conversión agotada tras {self._timeout}s") from exc
        except OSError as exc:
            raise ExportToolUnavailable(f"no se pudo ejecutar {args[0]}: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            tail = " | ".join(detail[-3:]) if detail else "sin detalle"
            raise ExportConversionFailed(f"conversión fallida: {tail}")

    @staticmethod
    def _find_output(base: Path, target: ExportFormat) -> Path:
        suffix = _OUTPUT_SUFFIX[target]
        direct = base.with_suffix(suffix)
        if direct.exists() and direct.stat().st_size > 0:
            return direct
        candidates = sorted(base.parent.glob(f"{base.name}*{suffix}"))
        for candidate in candidates:
            if candidate.stat().st_size > 0:
                return candidate
        raise ExportConversionFailed(f"el conversor no produjo {suffix}")
