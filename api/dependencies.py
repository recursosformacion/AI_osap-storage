from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

from domain.ports.repositories import StorageProviderRepository
from fastapi import Request
from infrastructure.config import Settings
from infrastructure.container import Container
from infrastructure.db.connection import Database

T = TypeVar("T")


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


def get_settings(request: Request) -> Settings:
    return cast(Container, request.app.state.container).settings


def get_db(request: Request) -> Database:
    return cast(Container, request.app.state.container).db


def get_provider_repo(request: Request) -> StorageProviderRepository:
    return cast(Container, request.app.state.container).provider_repo


def get_file_repo(request: Request):
    return cast(Container, request.app.state.container).file_repo


def _use_case(attr: str) -> Callable[..., T]:
    def resolver(request: Request) -> T:
        return cast(Container, request.app.state.container).__getattribute__(attr)

    return resolver


RegisterFileDep = _use_case("register_file")
GetFileDep = _use_case("get_file")
ListFilesDep = _use_case("list_files")
StartDownloadDep = _use_case("start_download")
GetDownloadJobDep = _use_case("get_download_job")
GetDownloadUrlDep = _use_case("get_download_url")
StreamFileDep = _use_case("stream_file")
CreateProviderDep = _use_case("create_provider")
GetProviderDep = _use_case("get_provider")
ListProvidersDep = _use_case("list_providers")
ResolveFileDep = _use_case("resolve_file")
SearchEntriesDep = _use_case("search_entries")
VerifyFileDep = _use_case("verify_file")
DeleteFileDep = _use_case("delete_file")
ListArchivesDep = _use_case("list_archives")
GetArchiveDep = _use_case("get_archive")
CountMissingEntriesDep = _use_case("count_missing_entries")
GetStatisticsDep = _use_case("get_statistics")
