from __future__ import annotations

import asyncio
import tarfile

from domain.ports.archives import ArchiveReader


class TarArchiveReader(ArchiveReader):
    def __init__(self, path: str) -> None:
        self._tar = tarfile.open(path, "r:*")  # noqa: SIM115 - se mantiene abierto para múltiples extract
        self._names = set(self._tar.getnames())

    def has_member(self, name: str) -> bool:
        return name in self._names

    async def extract(self, name: str, destination_path: str) -> None:
        member = self._tar.getmember(name)

        def _do() -> None:
            source = self._tar.extractfile(member)
            if source is None:
                raise OSError(f"no se pudo leer el miembro {name!r} del archivo")
            with open(destination_path, "wb") as fh:
                while chunk := source.read(1 << 16):
                    fh.write(chunk)

        await asyncio.to_thread(_do)

    def close(self) -> None:
        self._tar.close()


class TarArchiveReaderFactory:
    def open(self, path: str) -> ArchiveReader:
        return TarArchiveReader(path)
