from __future__ import annotations

import hashlib
import time
from pathlib import Path

from domain.entities.file import File
from domain.services.score_export import ExportFormat


class ExportCache:
    """Caché temporal de derivados; nunca se registra en la base de datos.

    La clave incluye el SHA-256 del original, el formato de salida y la versión del
    conversor. Los ficheros caducan y se eliminan de forma perezosa.
    """

    VERSION = "1"

    def __init__(self, root: Path, ttl_seconds: int = 3600) -> None:
        self._root = root
        self._ttl = max(0, ttl_seconds)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def key(self, file: File, source: ExportFormat, target: ExportFormat) -> str:
        seed = f"{file.sha256 or file.name}:{source.value}:{target.value}:{self.VERSION}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def path(self, key: str, target: ExportFormat) -> Path:
        suffix = {
            ExportFormat.MXL: ".mxl",
            ExportFormat.MUSICXML: ".musicxml",
            ExportFormat.LY: ".ly",
            ExportFormat.PDF: ".pdf",
            ExportFormat.MIDI: ".midi",
            ExportFormat.SVG: ".svg",
        }.get(target, ".bin")
        directory = self._root / key[:2]
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{key}{suffix}"

    def get(self, key: str, target: ExportFormat) -> Path | None:
        path = self.path(key, target)
        if not path.exists() or path.stat().st_size == 0:
            return None
        if self._ttl and time.time() - path.stat().st_mtime > self._ttl:
            path.unlink(missing_ok=True)
            return None
        return path

    def cleanup(self) -> None:
        if not self._ttl:
            return
        cutoff = time.time() - self._ttl
        for path in self._root.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
