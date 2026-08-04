from __future__ import annotations

from application.use_cases.import_pdmx import PdmxImporter, PdmxRow
from domain.entities.import_source import ImportSource
from tests.fakes import (
    InMemoryArchiveEntryRepository,
    InMemoryArchiveRepository,
    InMemoryImportSourceRepository,
)


async def test_import_builds_archives_and_entries():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    importer = PdmxImporter(archives, entries, batch_size=2)

    rows = [
        PdmxRow("mxl/a/000001.mxl", "pdmx-mxl-01.tar.gz", "http://x/1.tar.gz", "K1:MusicXML"),
        PdmxRow("mxl/a/000002.mxl", "pdmx-mxl-01.tar.gz", "http://x/1.tar.gz", None),
        PdmxRow("mxl/b/000001.mxl", "pdmx-mxl-02.tar.gz", "http://x/2.tar.gz", None),
    ]
    result = await importer.import_rows(rows)

    assert result.archives == 2
    assert result.entries == 3
    assert await entries.count_by_archive(1) == 2
    assert await entries.count_by_archive(2) == 1


async def test_import_is_idempotent():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    importer = PdmxImporter(archives, entries, batch_size=2)
    rows = [
        PdmxRow("mxl/a/000001.mxl", "pdmx-mxl-01.tar.gz", "http://x/1.tar.gz", "K1:MusicXML"),
        PdmxRow("mxl/a/000002.mxl", "pdmx-mxl-01.tar.gz", "http://x/1.tar.gz", None),
    ]

    first = await importer.import_rows(rows)
    second = await importer.import_rows(rows)

    assert first.archives == 1
    assert second.archives == 0  # archive reutilizado
    assert second.entries == 0  # entradas duplicadas descartadas
    assert await entries.count_by_archive(1) == 2


async def test_import_skips_empty_rows():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    importer = PdmxImporter(archives, entries)
    rows = [
        PdmxRow("", "pdmx-mxl-01.tar.gz"),
        PdmxRow("mxl/a/000001.mxl", ""),
        PdmxRow("mxl/a/000001.mxl", "pdmx-mxl-01.tar.gz"),
    ]
    result = await importer.import_rows(rows)
    assert result.entries == 1


async def test_import_records_import_source():
    archives = InMemoryArchiveRepository()
    entries = InMemoryArchiveEntryRepository()
    sources = InMemoryImportSourceRepository()
    importer = PdmxImporter(archives, entries, sources=sources)
    source = ImportSource(provider="pdmx", version="v2", csv_path="data/pdmx.csv")

    result = await importer.import_rows([PdmxRow("mxl/a/000001.mxl", "p.tar.gz")], source=source)

    assert result.entries == 1
    created = (await sources.list())[0]
    assert created.provider == "pdmx"
    assert created.version == "v2"
    assert created.csv_path == "data/pdmx.csv"
