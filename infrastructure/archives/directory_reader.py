from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from domain.ports.archives import ArchiveReader


class DirectoryArchiveReader(ArchiveReader):
    """Lee un Archive cuyo contenido ya está extraído en un directorio.

    `relative_path` (p. ej. "./mxl/1/11/x.mxl") se resuelve bajo la raíz del
    directorio, sin necesidad de descomprimir nada.
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def has_member(self, name: str) -> bool:
        return (self._root / name).is_file()

    async def extract(self, name: str, destination_path: str) -> None:
        await asyncio.to_thread(shutil.copy2, self._root / name, destination_path)

    def close(self) -> None:
        pass
