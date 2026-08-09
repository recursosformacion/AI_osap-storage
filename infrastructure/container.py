from __future__ import annotations

from dataclasses import dataclass

from application.services.file_publisher import FilePublisher
from application.services.mirror_resources import MirrorResourceRegistrar
from application.services.tar_downloader import TarDownloader
from application.use_cases.archives import CountMissingEntries, GetArchive, ListArchives
from application.use_cases.build_works import BuildWorks
from application.use_cases.composer_admin import (
    GetComposerDetail,
    GetComposerWorks,
    ListComposers,
    MergeComposers,
)
from application.use_cases.delete_file import DeleteFile
from application.use_cases.enrich_metadata import EnrichWork
from application.use_cases.get_download_job import GetDownloadJob
from application.use_cases.get_download_url import GetDownloadUrl
from application.use_cases.get_file import GetFile
from application.use_cases.import_pdmx import PdmxImporter
from application.use_cases.list_files import ListFiles
from application.use_cases.materialize_archive import MaterializeArchive
from application.use_cases.materialize_file import MaterializeFile
from application.use_cases.providers import CreateProvider, GetProvider, ListProviders
from application.use_cases.register_existing_file import RegisterExistingFile
from application.use_cases.register_file import RegisterFile
from application.use_cases.register_resources import RegisterMirrorResources
from application.use_cases.resolve_file import ResolveFile
from application.use_cases.search_entries import SearchEntries
from application.use_cases.start_download import StartDownload
from application.use_cases.statistics import GetStatistics, RefreshStatistics
from application.use_cases.stream_file import StreamFile
from application.use_cases.verify_file import VerifyFile
from application.use_cases.voting import (
    GetComposerStatistics,
    GetWorkStatistics,
    RecordVote,
    RefreshVotingStatistics,
)
from application.use_cases.works import GetWork, SearchWorks, SearchWorksFull
from domain.entities.storage_provider import ProviderType
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository
from domain.ports.composer_repository import ComposerRepository
from domain.ports.download import FileDownloader
from domain.ports.hashing import FileHasher
from domain.ports.repositories import (
    DownloadJobRepository,
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.ports.storage import StorageBackendRegistry
from domain.ports.tasks import TaskScheduler
from domain.ports.voting_repository import VotingRepository
from domain.ports.work_repository import WorkRepository
from domain.services.availability import AvailabilityService
from domain.services.composer_resolver import ComposerResolver
from domain.services.file_registration import FileRegistrationService
from domain.services.integrity import IntegrityService

from infrastructure.archives.factory import ArchiveReaderFactory
from infrastructure.config import Settings
from infrastructure.db.connection import Database
from infrastructure.downloaders.httpx_downloader import HttpxDownloader
from infrastructure.hashing.hashlib_hasher import HashlibHasher
from infrastructure.providers.cloudflare_r2 import CloudflareR2Backend
from infrastructure.providers.google_drive import GoogleDriveBackend
from infrastructure.providers.http_remote import HttpRemoteBackend
from infrastructure.providers.local_disk import LocalDiskBackend
from infrastructure.providers.registry import (
    StorageBackendRegistry as ConcreteStorageBackendRegistry,
)
from infrastructure.providers.s3 import S3Backend
from infrastructure.repositories.sql_archive_entry_repository import SqlArchiveEntryRepository
from infrastructure.repositories.sql_archive_repository import SqlArchiveRepository
from infrastructure.repositories.sql_composer_repository import SqlComposerRepository
from infrastructure.repositories.sql_file_repository import SqlFileRepository
from infrastructure.repositories.sql_import_source_repository import SqlImportSourceRepository
from infrastructure.repositories.sql_job_repository import SqlDownloadJobRepository
from infrastructure.repositories.sql_location_repository import SqlStorageLocationRepository
from infrastructure.repositories.sql_provider_repository import SqlStorageProviderRepository
from infrastructure.repositories.sql_statistics_repository import SqlStatisticsRepository
from infrastructure.repositories.sql_voting_repository import SqlVotingRepository
from infrastructure.repositories.sql_work_repository import SqlWorkRepository
from infrastructure.tasks.asyncio_scheduler import AsyncioTaskScheduler


@dataclass(frozen=True)
class Container:
    settings: Settings
    db: Database
    file_repo: FileRepository
    provider_repo: StorageProviderRepository
    location_repo: StorageLocationRepository
    job_repo: DownloadJobRepository
    archive_repo: ArchiveRepository
    archive_entry_repo: ArchiveEntryRepository
    work_repo: WorkRepository
    composer_repo: ComposerRepository
    composer_resolver: ComposerResolver
    voting_repo: VotingRepository
    list_composers: ListComposers
    get_composer_detail: GetComposerDetail
    get_composer_works: GetComposerWorks
    merge_composers: MergeComposers
    record_vote: RecordVote
    get_work_statistics: GetWorkStatistics
    get_composer_statistics: GetComposerStatistics
    refresh_voting_statistics: RefreshVotingStatistics
    downloader: FileDownloader
    hasher: FileHasher
    scheduler: TaskScheduler
    registry: StorageBackendRegistry
    register_file: RegisterFile
    get_file: GetFile
    list_files: ListFiles
    start_download: StartDownload
    get_download_job: GetDownloadJob
    get_download_url: GetDownloadUrl
    stream_file: StreamFile
    create_provider: CreateProvider
    get_provider: GetProvider
    list_providers: ListProviders
    publisher: FilePublisher
    import_pdmx: PdmxImporter
    resolve_file: ResolveFile
    search_entries: SearchEntries
    materialize_archive: MaterializeArchive
    materialize_file: MaterializeFile
    register_existing_file: RegisterExistingFile
    register_resources: RegisterMirrorResources
    verify_file: VerifyFile
    delete_file: DeleteFile
    list_archives: ListArchives
    get_archive: GetArchive
    count_missing_entries: CountMissingEntries
    refresh_statistics: RefreshStatistics
    get_statistics: GetStatistics
    build_works: BuildWorks
    search_works: SearchWorks
    search_works_full: SearchWorksFull
    get_work: GetWork
    enrich_work: EnrichWork


def build_container(settings: Settings) -> Container:
    db = Database(settings)

    file_repo = SqlFileRepository(db)
    provider_repo = SqlStorageProviderRepository(db)
    location_repo = SqlStorageLocationRepository(db)
    job_repo = SqlDownloadJobRepository(db)
    archive_repo = SqlArchiveRepository(db)
    archive_entry_repo = SqlArchiveEntryRepository(db)
    import_source_repo = SqlImportSourceRepository(db)
    statistics_repo = SqlStatisticsRepository(db)
    work_repo = SqlWorkRepository(db)
    composer_repo = SqlComposerRepository(db)
    composer_resolver = ComposerResolver(composer_repo)
    voting_repo = SqlVotingRepository(db)
    hasher = HashlibHasher()
    downloader = HttpxDownloader()
    scheduler = AsyncioTaskScheduler()

    registry = ConcreteStorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, LocalDiskBackend)
    registry.register(ProviderType.S3, S3Backend)
    registry.register(ProviderType.HTTP_REMOTE, HttpRemoteBackend)
    registry.register(ProviderType.GOOGLE_DRIVE, GoogleDriveBackend)
    registry.register(ProviderType.CLOUDFLARE_R2, CloudflareR2Backend)

    registration = FileRegistrationService(file_repo)
    integrity = IntegrityService(hasher)
    availability = AvailabilityService()

    register_file = RegisterFile(registration)
    get_file = GetFile(file_repo, location_repo, provider_repo, availability)
    list_files = ListFiles(file_repo, location_repo, provider_repo, availability)
    start_download = StartDownload(
        files=file_repo,
        jobs=job_repo,
        locations=location_repo,
        providers=provider_repo,
        downloader=downloader,
        integrity=integrity,
        registry=registry,
        scheduler=scheduler,
        temp_dir=settings.temp_dir,
    )
    get_download_job = GetDownloadJob(job_repo)
    get_download_url = GetDownloadUrl(file_repo, location_repo, provider_repo, availability, registry)
    stream_file = StreamFile(get_download_url, registry, archive_entry_repo)
    create_provider = CreateProvider(provider_repo, registry)
    get_provider = GetProvider(provider_repo)
    list_providers = ListProviders(provider_repo)

    publisher = FilePublisher(file_repo, location_repo, provider_repo, registry)
    tar_downloader = TarDownloader(downloader, None)
    import_pdmx = PdmxImporter(archive_repo, archive_entry_repo, sources=import_source_repo)
    resolve_file = ResolveFile(archive_entry_repo, archive_repo)
    search_entries = SearchEntries(archive_entry_repo, archive_repo)
    materialize_archive = MaterializeArchive(
        archives=archive_repo,
        entries=archive_entry_repo,
        reader_factory=ArchiveReaderFactory(),
        hasher=hasher,
        registration=registration,
        publisher=publisher,
        temp_dir=settings.temp_dir,
        tar_downloader=tar_downloader,
    )
    materialize_file = MaterializeFile(
        archives=archive_repo,
        entries=archive_entry_repo,
        reader_factory=ArchiveReaderFactory(),
        hasher=hasher,
        registration=registration,
        publisher=publisher,
        temp_dir=settings.temp_dir,
        tar_downloader=tar_downloader,
    )
    register_existing_file = RegisterExistingFile(hasher, registration, publisher)
    registrar = MirrorResourceRegistrar(file_repo, location_repo, archive_entry_repo)
    register_resources = RegisterMirrorResources(archive_repo, archive_entry_repo, provider_repo, registrar)
    verify_file = VerifyFile(file_repo, location_repo, provider_repo, registry, hasher, settings.temp_dir)
    delete_file = DeleteFile(file_repo, location_repo, provider_repo, registry)
    list_archives = ListArchives(archive_repo)
    get_archive = GetArchive(archive_repo)
    count_missing_entries = CountMissingEntries(archive_entry_repo)
    refresh_statistics = RefreshStatistics(archive_repo, archive_entry_repo, file_repo, statistics_repo)
    get_statistics = GetStatistics(refresh_statistics, statistics_repo)
    build_works = BuildWorks(archive_entry_repo, work_repo, composer_resolver)
    search_works = SearchWorks(work_repo, composer_resolver)
    search_works_full = SearchWorksFull(work_repo, archive_entry_repo, composer_resolver)
    get_work = GetWork(work_repo, archive_entry_repo, composer_resolver)
    enrich_work = EnrichWork(work_repo, composer_resolver)
    list_composers = ListComposers(composer_repo)
    get_composer_detail = GetComposerDetail(composer_repo)
    get_composer_works = GetComposerWorks(composer_repo)
    merge_composers = MergeComposers(composer_repo)
    record_vote = RecordVote(voting_repo, work_repo)
    get_work_statistics = GetWorkStatistics(voting_repo, work_repo)
    get_composer_statistics = GetComposerStatistics(voting_repo, composer_repo)
    refresh_voting_statistics = RefreshVotingStatistics(voting_repo)

    return Container(
        settings=settings,
        db=db,
        file_repo=file_repo,
        provider_repo=provider_repo,
        location_repo=location_repo,
        job_repo=job_repo,
        archive_repo=archive_repo,
        archive_entry_repo=archive_entry_repo,
        work_repo=work_repo,
        composer_repo=composer_repo,
        composer_resolver=composer_resolver,
        voting_repo=voting_repo,
        list_composers=list_composers,
        get_composer_detail=get_composer_detail,
        get_composer_works=get_composer_works,
        merge_composers=merge_composers,
        record_vote=record_vote,
        get_work_statistics=get_work_statistics,
        get_composer_statistics=get_composer_statistics,
        refresh_voting_statistics=refresh_voting_statistics,
        downloader=downloader,
        hasher=hasher,
        scheduler=scheduler,
        registry=registry,
        register_file=register_file,
        get_file=get_file,
        list_files=list_files,
        start_download=start_download,
        get_download_job=get_download_job,
        get_download_url=get_download_url,
        stream_file=stream_file,
        create_provider=create_provider,
        get_provider=get_provider,
        list_providers=list_providers,
        publisher=publisher,
        import_pdmx=import_pdmx,
        resolve_file=resolve_file,
        search_entries=search_entries,
        materialize_archive=materialize_archive,
        materialize_file=materialize_file,
        register_existing_file=register_existing_file,
        register_resources=register_resources,
        verify_file=verify_file,
        delete_file=delete_file,
        list_archives=list_archives,
        get_archive=get_archive,
        count_missing_entries=count_missing_entries,
        refresh_statistics=refresh_statistics,
        get_statistics=get_statistics,
        build_works=build_works,
        search_works=search_works,
        search_works_full=search_works_full,
        get_work=get_work,
        enrich_work=enrich_work,
    )
