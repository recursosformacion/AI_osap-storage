from __future__ import annotations

from urllib.parse import quote

from application.use_cases.delete_file import DeleteFile
from application.use_cases.get_download_url import DownloadTarget, GetDownloadUrl
from application.use_cases.get_file import FileDetail, GetFile
from application.use_cases.list_files import ListFiles
from application.use_cases.register_file import RegisterFile, RegisterFileCommand
from application.use_cases.start_download import StartDownload, StartDownloadCommand
from application.use_cases.stream_file import StreamFile
from application.use_cases.verify_file import VerifyFile
from domain.entities.storage_location import StorageLocation
from domain.entities.storage_provider import StorageProvider
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from infrastructure.config import Settings

from api.dependencies import (
    DeleteFileDep,
    GetDownloadUrlDep,
    GetFileDep,
    ListFilesDep,
    RegisterFileDep,
    StartDownloadDep,
    StreamFileDep,
    VerifyFileDep,
    get_settings,
)
from api.schemas import (
    DownloadJobRead,
    DownloadStart,
    DownloadUrlRead,
    FileCreate,
    FileRead,
    LocationRead,
    VerifyResultRead,
)

router = APIRouter(prefix="/api/v1/files", tags=["files"])


def _location_read(location: StorageLocation, provider: StorageProvider) -> LocationRead:
    return LocationRead(
        id=location.id,
        provider_id=location.provider_id,
        provider_name=provider.name,
        provider_type=provider.provider_type,
        object_key=location.object_key,
        status=location.status.value,
        created_at=location.created_at,
        updated_at=location.updated_at,
    )


def _provider_for(location: StorageLocation, providers_by_id: dict[int, StorageProvider]) -> StorageProvider:
    provider = providers_by_id.get(location.provider_id)
    if provider is None:
        raise RuntimeError(f"provider {location.provider_id} missing from provider list")
    return provider


def _file_read(detail: FileDetail) -> FileRead:
    providers_by_id = {p.id: p for p in detail.providers}
    locations = [
        _location_read(loc, _provider_for(loc, providers_by_id)) for loc in detail.locations
    ]
    return FileRead(
        id=detail.file.id,
        sha256=detail.file.sha256,
        name=detail.file.name,
        mime_type=detail.file.mime_type,
        size_bytes=detail.file.size_bytes,
        status=detail.file.status.value,
        available=detail.available,
        locations=locations,
        created_at=detail.file.created_at,
        updated_at=detail.file.updated_at,
    )


def _empty_file_read(file) -> FileRead:
    return FileRead(
        id=file.id,
        sha256=file.sha256,
        name=file.name,
        mime_type=file.mime_type,
        size_bytes=file.size_bytes,
        status=file.status.value,
        available=False,
        locations=[],
        created_at=file.created_at,
        updated_at=file.updated_at,
    )


@router.post("", response_model=FileRead, status_code=201)
async def register_file(
    payload: FileCreate,
    uc: RegisterFile = Depends(RegisterFileDep),
) -> FileRead:
    file = await uc.execute(RegisterFileCommand(**payload.model_dump()))
    return _empty_file_read(file)


@router.get("", response_model=list[FileRead])
async def list_files(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListFiles = Depends(ListFilesDep),
) -> list[FileRead]:
    details = await uc.execute(limit=limit, offset=offset)
    return [_file_read(detail) for detail in details]


@router.get("/{file_id}", response_model=FileRead)
async def get_file(
    file_id: int,
    uc: GetFile = Depends(GetFileDep),
) -> FileRead:
    return _file_read(await uc.execute(file_id))


@router.post("/{file_id}/downloads", response_model=DownloadJobRead, status_code=202)
async def start_download(
    file_id: int,
    payload: DownloadStart,
    uc: StartDownload = Depends(StartDownloadDep),
) -> DownloadJobRead:
    job = await uc.execute(
        StartDownloadCommand(
            file_id=file_id,
            source_url=payload.source_url,
            provider_id=payload.provider_id,
        )
    )
    return DownloadJobRead.model_validate(job)


@router.get("/{file_id}/url", response_model=DownloadUrlRead)
async def download_url(
    file_id: int,
    provider_id: int | None = Query(default=None),
    uc: GetDownloadUrl = Depends(GetDownloadUrlDep),
    settings: Settings = Depends(get_settings),
) -> DownloadUrlRead:
    target: DownloadTarget = await uc.execute(file_id, provider_id)
    url = target.native_url or (
        f"{settings.public_base_url.rstrip('/')}"
        f"/api/v1/files/{file_id}/content?provider_id={target.provider.id}"
    )
    return DownloadUrlRead(url=url, provider_id=target.provider.id)


@router.get("/{file_id}/content")
async def stream_file(
    file_id: int,
    provider_id: int | None = Query(default=None),
    uc: StreamFile = Depends(StreamFileDep),
) -> StreamingResponse:
    stream = await uc.execute(file_id, provider_id)
    headers = {
        "Content-Disposition": f'attachment; filename="{quote(stream.file.name)}"'
    }
    if stream.file.size_bytes is not None:
        headers["Content-Length"] = str(stream.file.size_bytes)
    return StreamingResponse(
        stream.content,
        media_type=stream.file.mime_type or "application/octet-stream",
        headers=headers,
    )


@router.post("/{file_id}/verify", response_model=VerifyResultRead)
async def verify_file(
    file_id: int,
    uc: VerifyFile = Depends(VerifyFileDep),
) -> VerifyResultRead:
    return VerifyResultRead.model_validate(await uc.execute(file_id))


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    uc: DeleteFile = Depends(DeleteFileDep),
) -> Response:
    await uc.execute(file_id)
    return Response(status_code=204)
