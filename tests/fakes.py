from __future__ import annotations

from pathlib import Path

from domain.entities.archive import Archive
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.download_job import DownloadJob
from domain.entities.file import File
from domain.entities.import_source import ImportSource
from domain.entities.statistics import Statistics
from domain.entities.storage_location import StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.entities.work import Work
from domain.exceptions import DownloadFailed
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository
from domain.ports.import_source_repository import ImportSourceRepository
from domain.ports.repositories import (
    DownloadJobRepository,
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.ports.statistics_repository import StatisticsRepository
from domain.ports.work_repository import WorkRepository


class InMemoryFileRepository(FileRepository):
    def __init__(self) -> None:
        self._files: dict[int, File] = {}
        self._by_sha: dict[str, File] = {}
        self._seq = 0

    async def create(self, file: File) -> File:
        self._seq += 1
        file.id = self._seq
        self._files[file.id] = file
        self._by_sha[file.sha256] = file
        return file

    async def bulk_create(self, files: list[File]) -> list[File]:
        for file in files:
            self._seq += 1
            file.id = self._seq
            self._files[file.id] = file
            if file.sha256:
                self._by_sha[file.sha256] = file
        return files

    async def get_by_id(self, file_id: int) -> File | None:
        return self._files.get(file_id)

    async def get_by_sha256(self, sha256: str) -> File | None:
        return self._by_sha.get(sha256)

    async def delete(self, file_id: int) -> None:
        file = self._files.pop(file_id, None)
        if file is not None:
            self._by_sha.pop(file.sha256, None)

    async def save(self, file: File) -> None:
        self._files[file.id] = file
        self._by_sha[file.sha256] = file

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[File]:
        items = sorted(self._files.values(), key=lambda f: f.id or 0, reverse=True)
        return items[offset : offset + limit]

    async def count(self) -> int:
        return len(self._files)

    async def sum_size(self) -> int:
        return sum(f.size_bytes or 0 for f in self._files.values())


class InMemoryProviderRepository(StorageProviderRepository):
    def __init__(self) -> None:
        self._providers: dict[int, StorageProvider] = {}
        self._seq = 0

    async def create(self, provider: StorageProvider) -> StorageProvider:
        self._seq += 1
        provider.id = self._seq
        self._providers[provider.id] = provider
        return provider

    async def get_by_id(self, provider_id: int) -> StorageProvider | None:
        return self._providers.get(provider_id)

    async def list(self, *, enabled_only: bool = True) -> list[StorageProvider]:
        return [
            p for p in self._providers.values() if (not enabled_only) or p.enabled
        ]

    async def save(self, provider: StorageProvider) -> None:
        self._providers[provider.id] = provider


class InMemoryLocationRepository(StorageLocationRepository):
    def __init__(self) -> None:
        self._locations: list[StorageLocation] = []
        self._seq = 0

    async def create(self, location: StorageLocation) -> StorageLocation:
        self._seq += 1
        location.id = self._seq
        self._locations.append(location)
        return location

    async def bulk_create(self, locations: list[StorageLocation]) -> None:
        for location in locations:
            self._seq += 1
            location.id = self._seq
            self._locations.append(location)

    async def get_by_id(self, location_id: int) -> StorageLocation | None:
        return next((loc for loc in self._locations if loc.id == location_id), None)

    async def get_by_file_and_provider(self, file_id: int, provider_id: int) -> StorageLocation | None:
        return next(
            (loc for loc in self._locations if loc.file_id == file_id and loc.provider_id == provider_id),
            None,
        )

    async def list_by_file(self, file_id: int) -> list[StorageLocation]:
        return [loc for loc in self._locations if loc.file_id == file_id]

    async def count(self) -> int:
        return len(self._locations)

    async def list_all(self, *, limit: int = 1000, offset: int = 0) -> list[StorageLocation]:
        return self._locations[offset : offset + limit]

    async def delete_by_file(self, file_id: int) -> None:
        self._locations = [loc for loc in self._locations if loc.file_id != file_id]

    async def save(self, location: StorageLocation) -> None:
        for i, loc in enumerate(self._locations):
            if loc.id == location.id:
                self._locations[i] = location
                return


class InMemoryJobRepository(DownloadJobRepository):
    def __init__(self) -> None:
        self._jobs: list[DownloadJob] = []
        self._seq = 0

    async def create(self, job: DownloadJob) -> DownloadJob:
        self._seq += 1
        job.id = self._seq
        self._jobs.append(job)
        return job

    async def get_by_id(self, job_id: int) -> DownloadJob | None:
        return next((j for j in self._jobs if j.id == job_id), None)

    async def save(self, job: DownloadJob) -> None:
        for i, j in enumerate(self._jobs):
            if j.id == job.id:
                self._jobs[i] = job
                return

    async def list_by_file(self, file_id: int) -> list[DownloadJob]:
        return [j for j in self._jobs if j.file_id == file_id]


class SyncScheduler:
    def __init__(self) -> None:
        self.scheduled: list = []

    def schedule(self, coro) -> None:
        self.scheduled.append(coro)


class FakeDownloader:
    def __init__(self, payload: bytes, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail

    async def download(self, source_url: str, destination_path: str) -> None:
        if self.fail:
            raise DownloadFailed("download failed")
        Path(destination_path).write_bytes(self.payload)


class MemoryBackend:
    provider_type = "local_disk"

    def __init__(self, config: dict) -> None:
        self._objects: dict[str, bytes] = {}

    async def store(self, local_path: str, object_key: str) -> None:
        self._objects[object_key] = Path(local_path).read_bytes()

    async def delete(self, object_key: str) -> None:
        self._objects.pop(object_key, None)

    async def exists(self, object_key: str) -> bool:
        return object_key in self._objects

    async def url_for(self, object_key: str) -> str | None:
        return None

    async def open_stream(self, object_key: str):
        data = self._objects[object_key]

        async def _gen():
            yield data

        return _gen()


class InMemoryArchiveRepository(ArchiveRepository):
    def __init__(self) -> None:
        self._items: dict[int, Archive] = {}
        self._seq = 0

    async def create(self, archive: Archive) -> Archive:
        self._seq += 1
        archive.id = self._seq
        self._items[archive.id] = archive
        return archive

    async def get_by_id(self, archive_id: int) -> Archive | None:
        return self._items.get(archive_id)

    async def get_by_name(self, name: str) -> Archive | None:
        return next((a for a in self._items.values() if a.name == name), None)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Archive]:
        items = sorted(self._items.values(), key=lambda a: a.id or 0, reverse=True)
        return items[offset : offset + limit]

    async def count(self) -> int:
        return len(self._items)

    async def count_downloaded(self) -> int:
        return len([a for a in self._items.values() if a.local_path])

    async def save(self, archive: Archive) -> None:
        self._items[archive.id] = archive


class InMemoryArchiveEntryRepository(ArchiveEntryRepository):
    def __init__(self) -> None:
        self._items: dict[int, ArchiveEntry] = {}
        self._seq = 0

    async def create(self, entry: ArchiveEntry) -> ArchiveEntry:
        self._seq += 1
        entry.id = self._seq
        self._items[entry.id] = entry
        return entry

    async def bulk_create(self, entries: list[ArchiveEntry]) -> int:
        added = 0
        for entry in entries:
            exists = next(
                (
                    e
                    for e in self._items.values()
                    if e.archive_id == entry.archive_id and e.relative_path == entry.relative_path
                ),
                None,
            )
            if exists:
                continue
            self._seq += 1
            entry.id = self._seq
            self._items[entry.id] = entry
            added += 1
        return added

    async def bulk_update_file_ids(self, entries: list[ArchiveEntry]) -> None:
        for entry in entries:
            if entry.id in self._items:
                self._items[entry.id].file_id = entry.file_id

    async def get_by_id(self, entry_id: int) -> ArchiveEntry | None:
        return self._items.get(entry_id)

    async def get_by_relative_path(self, relative_path: str) -> ArchiveEntry | None:
        return next((e for e in self._items.values() if e.relative_path == relative_path), None)

    async def get_by_logical_id(self, logical_id: str) -> ArchiveEntry | None:
        return next((e for e in self._items.values() if e.logical_id == logical_id), None)

    async def get_by_file_id(self, file_id: int) -> ArchiveEntry | None:
        return next((e for e in self._items.values() if e.file_id == file_id), None)

    async def list_by_archive(self, archive_id: int) -> list[ArchiveEntry]:
        return [e for e in self._items.values() if e.archive_id == archive_id]

    async def list_by_work(self, work_id: int) -> list[ArchiveEntry]:
        return [e for e in self._items.values() if e.work_id == work_id]

    async def list_all(self, *, limit: int = 1000, offset: int = 0) -> list[ArchiveEntry]:
        items = sorted(self._items.values(), key=lambda e: e.id or 0)
        return items[offset : offset + limit]

    async def bulk_update_work_ids(self, entries: list[ArchiveEntry]) -> None:
        for entry in entries:
            if entry.id in self._items:
                self._items[entry.id].work_id = entry.work_id

    async def search(self, query: str, *, limit: int = 50, offset: int = 0) -> list[ArchiveEntry]:
        q = query.lower()
        matches = [
            e
            for e in self._items.values()
            if (
                (e.logical_id and q in e.logical_id.lower())
                or (e.composer and q in e.composer.lower())
                or (e.title and q in e.title.lower())
                or q in e.relative_path.lower()
            )
        ]
        return sorted(matches, key=lambda e: e.id or 0)[offset : offset + limit]

    async def list_relative_paths(self) -> list[str]:
        return [e.relative_path for e in self._items.values()]

    async def count_total(self) -> int:
        return len(self._items)

    async def count_by_status(self, status: ArchiveEntryStatus) -> int:
        return len([e for e in self._items.values() if e.status == status])

    async def save(self, entry: ArchiveEntry) -> None:
        self._items[entry.id] = entry

    async def count_by_archive(self, archive_id: int) -> int:
        return len([e for e in self._items.values() if e.archive_id == archive_id])


class FakeArchiveReader:
    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    def has_member(self, name: str) -> bool:
        return name in self._files

    async def extract(self, name: str, destination_path: str) -> None:
        Path(destination_path).write_bytes(self._files[name])

    def close(self) -> None:
        pass


class FakeArchiveReaderFactory:
    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    def open(self, path: str, format: str = "tar") -> FakeArchiveReader:
        return FakeArchiveReader(self._files)


class InMemoryImportSourceRepository(ImportSourceRepository):
    def __init__(self) -> None:
        self._items: dict[int, ImportSource] = {}
        self._seq = 0

    async def create(self, source: ImportSource) -> ImportSource:
        self._seq += 1
        source.id = self._seq
        self._items[source.id] = source
        return source

    async def get_by_id(self, source_id: int) -> ImportSource | None:
        return self._items.get(source_id)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[ImportSource]:
        items = sorted(self._items.values(), key=lambda s: s.id or 0, reverse=True)
        return items[offset : offset + limit]


class InMemoryStatisticsRepository(StatisticsRepository):
    def __init__(self) -> None:
        self._latest: Statistics | None = None
        self._seq = 0

    async def get_latest(self) -> Statistics | None:
        return self._latest

    async def save(self, stats: Statistics) -> Statistics:
        self._seq += 1
        stats.id = self._seq
        self._latest = stats
        return stats


class InMemoryWorkRepository(WorkRepository):
    def __init__(self) -> None:
        self._items: dict[int, Work] = {}
        self._seq = 0

    async def create(self, work: Work) -> Work:
        self._seq += 1
        work.id = self._seq
        self._items[work.id] = work
        return work

    async def get_by_id(self, work_id: int) -> Work | None:
        return self._items.get(work_id)

    async def get_by_work_key(self, work_key: str) -> Work | None:
        return next((w for w in self._items.values() if w.work_key == work_key), None)

    async def search(self, query: str, *, limit: int = 50, offset: int = 0) -> list[Work]:
        q = query.lower()
        matches = [
            w
            for w in self._items.values()
            if (w.composer and q in w.composer.lower()) or (w.title and q in w.title.lower())
        ]
        return sorted(matches, key=lambda w: w.id or 0)[offset : offset + limit]

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Work]:
        items = sorted(self._items.values(), key=lambda w: w.id or 0)
        return items[offset : offset + limit]

    async def count(self) -> int:
        return len(self._items)
