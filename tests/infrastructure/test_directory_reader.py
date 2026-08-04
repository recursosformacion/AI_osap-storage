from __future__ import annotations

import asyncio
import io

from infrastructure.archives.directory_reader import DirectoryArchiveReader
from infrastructure.archives.factory import ArchiveReaderFactory


def test_directory_reader_resolves_relative_path(tmp_path):
    root = tmp_path / "root"
    (root / "mxl" / "1" / "11").mkdir(parents=True)
    file = root / "mxl" / "1" / "11" / "x.mxl"
    file.write_bytes(b"<score/>")

    reader = DirectoryArchiveReader(str(root))
    assert reader.has_member("./mxl/1/11/x.mxl") is True
    assert reader.has_member("./mxl/1/11/no.mxl") is False

    dest = tmp_path / "out.mxl"
    asyncio.run(reader.extract("./mxl/1/11/x.mxl", str(dest)))
    assert dest.read_bytes() == b"<score/>"
    reader.close()


def test_factory_dispatches_directory_vs_tar(tmp_path):
    import tarfile

    from infrastructure.archives.directory_reader import DirectoryArchiveReader
    from infrastructure.archives.tar_reader import TarArchiveReader

    tar_path = tmp_path / "x.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.addfile(tarfile.TarInfo("mxl/a.mxl"), io.BytesIO(b"<score/>"))

    factory = ArchiveReaderFactory()
    assert isinstance(factory.open(str(tmp_path), "directory"), DirectoryArchiveReader)
    assert isinstance(factory.open(str(tar_path), "tar.gz"), TarArchiveReader)
