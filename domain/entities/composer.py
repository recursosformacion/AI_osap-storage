from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


class ComposerStatus:
    ACTIVE = "active"
    MERGED = "merged"


@dataclass
class Composer:
    """Identidad canónica de un compositor mantenida por Storage.

    `id` es un UUID estable y opaco; `name` es el nombre canónico que Storage
    devuelve en las Works. Los nombres procedentes de proveedores se resuelven
    contra la tabla de alias (ver composer_aliases).
    """

    id: str
    name: str
    status: str = ComposerStatus.ACTIVE
    merged_into: str | None = None
    merged_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ComposerAlias:
    """Un nombre (alias) conocido que apunta a la identidad canónica de un compositor.

    `normalized_alias` es la forma normalizada de `alias`, usada para la resolución
    determinista. Un mismo `normalized_alias` no puede apuntar a dos compositores
    (restricción UNIQUE en BD).
    """

    composer_id: str
    alias: str
    normalized_alias: str
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ComposerSummary:
    """Fila ligera del listado administrativo (sin cargar aliases ni Works)."""

    id: str
    name: str
    status: str
    aliases_count: int = 0
    works_count: int = 0


@dataclass(frozen=True)
class ComposerDetail:
    """Detalle administrativo de un compositor."""

    id: str
    name: str
    status: str
    aliases: list[str] = field(default_factory=list)
    works_count: int = 0
    merged_into: str | None = None
    merged_at: datetime | None = None


@dataclass(frozen=True)
class ComposerWorkRef:
    """Referencia ligera de una Work asociada a un compositor."""

    work_id: int
    title: str | None = None
    composer_id: str | None = None


@dataclass(frozen=True)
class MergeComposersResult:
    target_id: str
    sources_merged: list[str]
    aliases_transferred: int
    works_moved: int
    merge_operation_id: str
