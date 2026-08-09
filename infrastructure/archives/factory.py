from __future__ import annotations

from domain.ports.archives import ArchiveReader

from infrastructure.archives.directory_reader import DirectoryArchiveReader
from infrastructure.archives.tar_reader import TarArchiveReader

DIRECTORY_FORMATS = {"directory", "dir", "folder"}


class ArchiveReaderFactory:
    """Elige el lector según el formato del Archive."""

    def open(self, path: str, format: str = "tar") -> ArchiveReader:
        fmt = (format or "tar").lower()
        if fmt in DIRECTORY_FORMATS:
            return DirectoryArchiveReader(path)
        return TarArchiveReader(path)
