from __future__ import annotations

from application.use_cases.stream_file import friendly_filename
from domain.entities.archive_entry import ArchiveEntry
from domain.entities.file import File


def test_friendly_filename_uses_title_and_composer():
    file = File(sha256=None, name="Qmhash.mxl", id=1)
    entry = ArchiveEntry(
        archive_id=1,
        relative_path="./mxl/1/1/Qmhash.mxl",
        composer="W.A. Mozart",
        title="Sinfonia 40",
        file_id=1,
    )
    assert friendly_filename(file, entry) == "W.A. Mozart - Sinfonia 40.mxl"


def test_friendly_filename_falls_back_to_file_name():
    file = File(sha256=None, name="Qmhash.mxl", id=1)
    assert friendly_filename(file, None) == "Qmhash.mxl"
