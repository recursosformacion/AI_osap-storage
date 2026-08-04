from __future__ import annotations

from domain.entities.file import SHA256_PATTERN, File, FileStatus
from domain.exceptions import InvalidFileData, InvalidSha256
from domain.ports.repositories import FileRepository


class FileRegistrationService:
    """Reglas de registro de ficheros: validación de SHA256 y deduplicación."""

    def __init__(self, files: FileRepository) -> None:
        self._files = files

    async def register(
        self,
        sha256: str,
        name: str,
        mime_type: str | None = None,
        size_bytes: int | None = None,
    ) -> File:
        normalized = self._normalize_sha256(sha256)
        self._validate_name(name)

        existing = await self._files.get_by_sha256(normalized)
        if existing is not None:
            return existing

        return await self._files.create(
            File(
                sha256=normalized,
                name=name.strip(),
                mime_type=mime_type,
                size_bytes=size_bytes,
                status=FileStatus.REGISTERED,
            )
        )

    @staticmethod
    def _normalize_sha256(sha256: str) -> str:
        if not sha256:
            raise InvalidSha256("sha256 is required")
        normalized = sha256.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise InvalidSha256("sha256 must be a 64-character lowercase hex string")
        return normalized

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.strip():
            raise InvalidFileData("name must not be empty")
