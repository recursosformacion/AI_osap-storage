"""Excepciones del dominio."""


class DomainError(Exception):
    """Error base del dominio."""


class EntityNotFound(DomainError):
    def __init__(self, entity: str, entity_id: int) -> None:
        super().__init__(f"{entity} with id {entity_id} not found")
        self.entity = entity
        self.entity_id = entity_id


class InvalidSha256(DomainError):
    pass


class InvalidFileData(DomainError):
    pass


class IntegrityVerificationError(DomainError):
    pass


class FileNotAvailable(DomainError):
    pass


class DownloadFailed(DomainError):
    pass


class UnsupportedProvider(DomainError):
    pass
