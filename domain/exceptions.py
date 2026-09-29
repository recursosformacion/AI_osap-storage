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


class DuplicateComposerAlias(DomainError):
    """Un normalized_alias ya apunta a otro compositor; conflicto de datos no resoluble."""

    def __init__(self, normalized_alias: str) -> None:
        super().__init__(f"normalized_alias '{normalized_alias}' already belongs to a composer")
        self.normalized_alias = normalized_alias


class InvalidMerge(DomainError):
    """Una operación de fusión de compositores es inválida."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DuplicateVote(DomainError):
    """El usuario ya votó esa obra en ese día."""

    def __init__(self, user_id: str, work_id: int) -> None:
        super().__init__(f"user {user_id} already voted work {work_id} today")
        self.user_id = user_id
        self.work_id = work_id


class InvalidTableCrud(DomainError):
    """Operación de CRUD genérico no permitida (tabla/columna inválida)."""


class ProposalStateError(DomainError):
    """La propuesta no está en `pending`: no admite revisión ni transición.

    `status` puede ser None cuando la transición falló por una carrera (otra revisión la
    cambió entre la lectura y la escritura).
    """

    def __init__(self, status: str | None = None) -> None:
        detail = f" (status={status})" if status else ""
        super().__init__(f"proposal is not pending{detail}")
        self.status = status


class ProposalAssignmentError(DomainError):
    """La fila de `works_person_roles` no se insertó: la propuesta no puede quedar aceptada.

    Evita aceptar una propuesta sin relación real (INSERT IGNORE silencioso) o auditar una
    asignación que no existe.
    """

