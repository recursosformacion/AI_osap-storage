from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from domain.entities.archive import Archive
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.composer import (
    Composer,
    ComposerAlias,
    ComposerDetail,
    ComposerStatus,
    ComposerSummary,
    ComposerWorkRef,
    MergeComposersResult,
)
from domain.entities.download_job import DownloadJob
from domain.entities.file import File
from domain.entities.import_source import ImportSource
from domain.entities.statistics import Statistics
from domain.entities.storage_location import StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.entities.voting import (
    ComposerStatistics,
    StatisticsRun,
    Vote,
    WorkStatistics,
)
from domain.entities.work import Work, WorkLists
from domain.exceptions import DownloadFailed
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository
from domain.ports.composer_repository import ComposerRepository
from domain.ports.import_source_repository import ImportSourceRepository
from domain.ports.repositories import (
    DownloadJobRepository,
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.ports.statistics_repository import StatisticsRepository
from domain.ports.voting_repository import VotingRepository
from domain.ports.work_repository import WorkRepository
from domain.services.composer_names import normalize_composer_name


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

    async def list_by_work_ids(self, work_ids: list[int]) -> list[ArchiveEntry]:
        ids = set(work_ids)
        return [e for e in self._items.values() if e.work_id in ids]

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


class InMemoryComposerRepository(ComposerRepository):
    def __init__(self) -> None:
        self._composers: dict[str, Composer] = {}
        self._aliases: dict[str, list[ComposerAlias]] = {}
        self._by_normalized: dict[str, str] = {}
        # work_id -> (composer_id, title)
        self._works: dict[int, tuple[str, str | None]] = {}
        self._history: list[dict] = []
        self._seq = 0

    def set_work(self, work_id: int, composer_id: str, title: str | None = None) -> None:
        self._works[work_id] = (composer_id, title)

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    async def create(self, composer: Composer) -> Composer:
        if not composer.id:
            composer.id = f"uuid-{len(self._composers) + 1}"
        composer.status = composer.status or "active"
        self._composers[composer.id] = composer
        self._aliases.setdefault(composer.id, [])
        return composer

    async def get_by_id(self, composer_id: str) -> Composer | None:
        return self._composers.get(composer_id)

    async def add_alias(self, composer_id: str, alias: str, normalized_alias: str) -> ComposerAlias:
        if normalized_alias in self._by_normalized and self._by_normalized[normalized_alias] != composer_id:
            from domain.exceptions import DuplicateComposerAlias

            raise DuplicateComposerAlias(normalized_alias)
        self._seq += 1
        entry = ComposerAlias(
            id=self._seq,
            composer_id=composer_id,
            alias=alias,
            normalized_alias=normalized_alias,
        )
        self._aliases.setdefault(composer_id, []).append(entry)
        self._by_normalized[normalized_alias] = composer_id
        return entry

    async def resolve_by_normalized(self, normalized: str) -> tuple[str, str] | None:
        composer_id = self._by_normalized.get(normalized)
        if composer_id is None:
            return None
        return await self._canonical_of(composer_id)

    async def resolve_many_by_normalized(
        self, normalized: list[str]
    ) -> dict[str, tuple[str, str]]:
        result: dict[str, tuple[str, str]] = {}
        for norm in normalized:
            cid = self._by_normalized.get(norm)
            if cid is not None:
                canonical = await self._canonical_of(cid)
                if canonical is not None:
                    result[norm] = canonical
        return result

    async def _canonical_of(self, composer_id: str) -> tuple[str, str] | None:
        current = self._composers.get(composer_id)
        seen: set[str] = set()
        while current is not None and current.status == "merged" and current.merged_into:
            if current.id in seen or current.merged_into not in self._composers:
                return None
            seen.add(current.id)
            current = self._composers[current.merged_into]
        if current is None:
            return None
        return (current.id, current.name)

    async def list_aliases(self, composer_id: str) -> list[ComposerAlias]:
        return list(self._aliases.get(composer_id, []))

    async def list_summaries(
        self, *, limit: int, offset: int, q: str | None = None
    ) -> list[ComposerSummary]:
        items = [c for c in self._composers.values() if c.status == "active"]
        if q:
            norm = normalize_composer_name(q)
            raw = q.strip().lower()
            matched = []
            for c in items:
                if raw in c.name.lower():
                    matched.append(c)
                    continue
                for a in self._aliases.get(c.id, []):
                    if norm and norm in a.normalized_alias:
                        matched.append(c)
                        break
            items = matched
        items.sort(key=lambda c: c.name)
        page = items[offset : offset + limit]
        return [
            ComposerSummary(
                id=c.id,
                name=c.name,
                status=c.status,
                aliases_count=len(self._aliases.get(c.id, [])),
                works_count=sum(1 for (wid, _) in self._works.values() if wid == c.id),
            )
            for c in page
        ]

    async def get_detail(self, composer_id: str):
        composer = self._composers.get(composer_id)
        if composer is None:
            return None
        return ComposerDetail(
            id=composer.id,
            name=composer.name,
            status=composer.status,
            aliases=[a.alias for a in self._aliases.get(composer.id, [])],
            works_count=sum(1 for (wid, _) in self._works.values() if wid == composer_id),
            merged_into=composer.merged_into,
            merged_at=composer.merged_at,
        )

    async def list_works(self, composer_id: str, *, limit: int, offset: int):
        rows = [(wid, cid, t) for (wid, (cid, t)) in self._works.items() if cid == composer_id]
        rows.sort(key=lambda r: r[0])
        return [
            ComposerWorkRef(work_id=wid, title=t, composer_id=cid)
            for (wid, cid, t) in rows[offset : offset + limit]
        ]

    async def count(self, q: str | None = None) -> int:
        return len(await self.list_summaries(limit=10**9, offset=0, q=q))

    async def merge(self, target_id: str, source_ids: list[str], *, merged_by: str | None = None):
        from domain.exceptions import EntityNotFound, InvalidMerge

        source_ids = list(dict.fromkeys(source_ids))
        if not source_ids:
            raise InvalidMerge("source_ids cannot be empty")
        if target_id in source_ids:
            raise InvalidMerge("target cannot appear among source_ids")

        target = self._composers.get(target_id)
        if target is None:
            raise EntityNotFound("composer", target_id)
        if target.status == ComposerStatus.MERGED:
            raise InvalidMerge(f"target composer {target_id} is already merged")

        for sid in source_ids:
            if sid not in self._composers:
                raise EntityNotFound("composer", sid)

        to_merge: list[str] = []
        for sid in source_ids:
            s = self._composers[sid]
            if s.status == ComposerStatus.MERGED:
                if s.merged_into == target_id:
                    continue
                raise InvalidMerge(f"source composer {sid} is already merged into {s.merged_into}")
            to_merge.append(sid)

        if not to_merge:
            return MergeComposersResult(
                target_id=target_id, sources_merged=[], aliases_transferred=0,
                works_moved=0, merge_operation_id="op-noop",
            )

        aliases_transferred = 0
        for sid in to_merge:
            for alias in self._aliases.get(sid, []):
                self._aliases.setdefault(target_id, []).append(alias)
                alias.composer_id = target_id
                self._by_normalized[alias.normalized_alias] = target_id
                aliases_transferred += 1
            self._aliases[sid] = []

        works_moved = 0
        for work_id, (cid, title) in list(self._works.items()):
            if cid in to_merge:
                self._works[work_id] = (target_id, title)
                works_moved += 1

        op = f"op-{len(self._history) + 1}"
        for sid in to_merge:
            s = self._composers[sid]
            s.status = ComposerStatus.MERGED
            s.merged_into = target_id
            self._history.append({
                "merge_operation_id": op, "source": sid, "target": target_id, "by": merged_by,
            })

        return MergeComposersResult(
            target_id=target_id, sources_merged=to_merge,
            aliases_transferred=aliases_transferred, works_moved=works_moved,
            merge_operation_id=op,
        )


class InMemoryVotingRepository(VotingRepository):
    def __init__(self) -> None:
        self._votes: list[Vote] = []
        self._seq = 0
        # work_id -> composer_id
        self._works: dict[int, str] = {}
        self._work_stats: dict[int, WorkStatistics] = {}
        self._composer_stats: dict[str, ComposerStatistics] = {}

    def set_work(self, work_id: int, composer_id: str) -> None:
        self._works[work_id] = composer_id

    async def add_vote(self, user_id: str, work_id: int, vote: int) -> Vote:
        from domain.exceptions import DuplicateVote

        if vote < 1 or vote > 5:
            raise ValueError("vote must be between 1 and 5")
        day = datetime.now(UTC).date()
        for v in self._votes:
            if v.user_id == user_id and v.work_id == work_id and v.vote_day == day:
                raise DuplicateVote(user_id, work_id)
        self._seq += 1
        entry = Vote(id=self._seq, user_id=user_id, work_id=work_id, vote=vote,
                     vote_day=day, voted_at=datetime.now(UTC))
        self._votes.append(entry)
        return entry

    async def get_work_statistics(self, work_id: int) -> WorkStatistics | None:
        return self._work_stats.get(work_id)

    async def get_work_statistics_bulk(self, work_ids: list[int]) -> dict[int, WorkStatistics]:
        return {wid: self._work_stats[wid] for wid in work_ids if wid in self._work_stats}

    async def get_composer_statistics(self, composer_id: str) -> ComposerStatistics | None:
        return self._composer_stats.get(composer_id)

    async def recompute_all(self) -> StatisticsRun:
        from collections import defaultdict

        from domain.services.rating import adjusted_rating, composer_rating, confidence

        work_votes: dict[int, list[int]] = defaultdict(list)
        for v in self._votes:
            work_votes[v.work_id].append(v.vote)
        all_votes = [x for vs in work_votes.values() for x in vs]
        global_mean = (sum(all_votes) / len(all_votes)) if all_votes else 0.0

        self._work_stats = {}
        for wid, vs in work_votes.items():
            rating = sum(vs) / len(vs)
            self._work_stats[wid] = WorkStatistics(
                work_id=wid,
                rating=rating,
                adjusted_rating=adjusted_rating(len(vs), rating, global_mean),
                vote_count=len(vs),
                work_count=1,
                confidence=confidence(len(vs)),
                calculated_at=datetime.now(UTC),
            )

        comp_works: dict[str, set[int]] = defaultdict(set)
        for wid, cid in self._works.items():
            comp_works[cid].add(wid)

        self._composer_stats = {}
        for cid, wids in comp_works.items():
            adjusted = [self._work_stats[wid].adjusted_rating for wid in wids if wid in self._work_stats]
            vcounts = [self._work_stats[wid].vote_count for wid in wids if wid in self._work_stats]
            total_votes = sum(vcounts)
            self._composer_stats[cid] = ComposerStatistics(
                composer_id=cid,
                rating=composer_rating(adjusted, vcounts),
                adjusted_rating=composer_rating(adjusted, vcounts),
                vote_count=total_votes,
                work_count=len(wids),
                confidence=confidence(total_votes),
                calculated_at=datetime.now(UTC),
            )
        return StatisticsRun(started_at=datetime.now(UTC), finished_at=datetime.now(UTC),
                             works_updated=len(self._work_stats),
                             composers_updated=len(self._composer_stats))


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
        self._lists: dict[str, dict[int, list[str]]] = {
            "tags": {},
            "genres": {},
            "instruments": {},
            "parts": {},
        }
        self._seq = 0

    async def create(self, work: Work) -> Work:
        self._seq += 1
        work.id = self._seq
        self._items[work.id] = work
        return work

    async def update(self, work: Work) -> None:
        self._items[work.id] = work

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

    async def all_(self, *, limit: int = 100, offset: int = 0) -> list[Work]:
        return await self.list_all(limit=limit, offset=offset)

    async def list_all(self, *, limit: int = 1000, offset: int = 0) -> list[Work]:
        items = sorted(self._items.values(), key=lambda w: w.id or 0)
        return items[offset : offset + limit]

    async def count(self) -> int:
        return len(self._items)

    async def replace_tags(self, work_id: int, tags: list[str]) -> None:
        self._lists["tags"][work_id] = list(tags)

    async def replace_genres(self, work_id: int, genres: list[str]) -> None:
        self._lists["genres"][work_id] = list(genres)

    async def replace_instruments(self, work_id: int, instruments: list[str]) -> None:
        self._lists["instruments"][work_id] = list(instruments)

    async def replace_parts(self, work_id: int, parts: list[str]) -> None:
        self._lists["parts"][work_id] = list(parts)

    async def get_tags(self, work_id: int) -> list[str]:
        return self._lists["tags"].get(work_id, [])

    async def get_genres(self, work_id: int) -> list[str]:
        return self._lists["genres"].get(work_id, [])

    async def get_instruments(self, work_id: int) -> list[str]:
        return self._lists["instruments"].get(work_id, [])

    async def get_parts(self, work_id: int) -> list[str]:
        return self._lists["parts"].get(work_id, [])

    async def get_lists_bulk(self, work_ids: list[int]) -> dict[int, WorkLists]:
        return {
            wid: WorkLists(
                tags=self._lists["tags"].get(wid, []),
                genres=self._lists["genres"].get(wid, []),
                instruments=self._lists["instruments"].get(wid, []),
                parts_names=self._lists["parts"].get(wid, []),
            )
            for wid in work_ids
        }
