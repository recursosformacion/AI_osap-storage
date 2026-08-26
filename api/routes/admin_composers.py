from __future__ import annotations

from typing import Any

from application.use_cases.composer_admin import (
    AddAlias,
    ComposerReviewStats,
    CreateComposer,
    DeleteComposerIdentifier,
    GetComposerBiography,
    GetComposerDetail,
    GetComposerWorks,
    ListAliases,
    ListComposers,
    MergeComposers,
    MoveAlias,
    PromoteAlias,
    ReviewComposer,
    SetAttribution,
    UpdateComposer,
    UpdateComposerBiography,
)
from fastapi import APIRouter, Depends, Query

from api.dependencies import (
    AddAliasDep,
    ComposerReviewStatsDep,
    CreateComposerDep,
    DeleteComposerIdentifierDep,
    GetComposerBiographyDep,
    GetComposerDetailDep,
    GetComposerWorksDep,
    ListAliasesDep,
    ListComposersDep,
    MergeComposersDep,
    MoveAliasDep,
    PromoteAliasDep,
    ReviewComposerDep,
    SetAttributionDep,
    UpdateComposerBiographyDep,
    UpdateComposerDep,
)
from api.schemas import (
    AddAliasRequest,
    AliasRead,
    BiographyUpdateRequest,
    ComposerAdminDetail,
    ComposerAdminListResult,
    ComposerAdminRead,
    ComposerReviewRequest,
    ComposerUpdateRequest,
    ComposerWorkRefRead,
    ComposerWorksResult,
    CreateComposerRequest,
    MergeComposersRequest,
    MergeComposersResultRead,
    MoveAliasRequest,
    MoveAliasResultRead,
    PromoteAliasResultRead,
    SetAttributionRequest,
    SetAttributionResultRead,
)

router = APIRouter(prefix="/api/admin/composers", tags=["admin-composers"])


@router.get(
    "/stats",
    summary="Composer review statistics",
    description="Conteo de compositores activos por review_status (total, correct, "
    "incorrect, reviewed, not_reviewed), más el acumulado del índice de autoridad "
    "(Metabrainz) y la fecha de la última sincronización.",
)
async def composer_review_stats(uc: ComposerReviewStats = Depends(ComposerReviewStatsDep)) -> dict[str, Any]:
    return await uc.execute()


@router.post(
    "",
    response_model=ComposerAdminRead,
    status_code=201,
    summary="Crear compositor",
    description="Crea un compositor con el nombre dado (para fusionar hacia un compositor "
    "inexistente). Si ya existe uno activo con ese nombre, devuelve ese.",
)
async def create_composer(
    payload: CreateComposerRequest,
    uc: CreateComposer = Depends(CreateComposerDep),
) -> ComposerAdminRead:
    result = await uc.execute(payload.name)
    return ComposerAdminRead.model_validate(result)


@router.get(
    "",
    response_model=ComposerAdminListResult,
    summary="Listar compositores",
    description="Listado administrativo paginado de compositores activos. "
    "Filtra por nombre o alias con la misma normalización del resolver, y opcionalmente "
    "por estado de revisión (?review=correct|false|pending).",
)
async def list_composers(
    q: str | None = Query(default=None, description="Filtro por nombre o alias"),
    review: str | None = Query(default=None, description="Filtro por review_status"),
    visible: str = Query(
        default="visible",
        pattern=r"^(visible|hidden|all)$",
        description="Filtro de visibilidad: visible (visible=1) | hidden (visible=0) | all (todos)",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListComposers = Depends(ListComposersDep),
) -> ComposerAdminListResult:
    result = await uc.execute(limit=limit, offset=offset, q=q, review=review, visible=visible)
    return ComposerAdminListResult(
        items=[ComposerAdminRead.model_validate(i) for i in result.items],
        total=result.total,
    )


@router.get(
    "/candidates",
    response_model=ComposerAdminListResult,
    summary="Candidatos a fusión",
    description="Asistencia a la revisión manual: devuelve compositores activos que "
    "coinciden con la búsqueda por nombre o alias. Nunca ejecuta fusiones automáticas.",
)
async def composer_candidates(
    q: str = Query(default="", description="Texto a buscar por nombre o alias"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListComposers = Depends(ListComposersDep),
) -> ComposerAdminListResult:
    result = await uc.execute(limit=limit, offset=offset, q=q or None)
    return ComposerAdminListResult(
        items=[ComposerAdminRead.model_validate(i) for i in result.items],
        total=result.total,
    )


@router.get(
    "/{composer_id}",
    response_model=ComposerAdminDetail,
    summary="Detalle de un compositor",
    description="Devuelve el compositor con sus aliases, works_count, estado y referencia de fusión.",
)
async def get_composer(
    composer_id: str,
    uc: GetComposerDetail = Depends(GetComposerDetailDep),
) -> ComposerAdminDetail:
    return ComposerAdminDetail.model_validate(await uc.execute(composer_id))


@router.put(
    "/{composer_id}",
    response_model=ComposerAdminDetail,
    summary="Editar identidad de un compositor",
    description="Edita campos de identidad (name, status, visible, fechas, cluster, "
    "review_status, review_reason, musicbrainz_id). Solo se actualizan los campos enviados.",
)
async def update_composer(
    composer_id: str,
    payload: ComposerUpdateRequest,
    uc: UpdateComposer = Depends(UpdateComposerDep),
) -> ComposerAdminDetail:
    detail = await uc.execute(
        composer_id,
        name=payload.name,
        status=payload.status,
        visible=payload.visible,
        birth_year=payload.birth_year,
        death_year=payload.death_year,
        cluster_id=payload.cluster_id,
        review_status=payload.review_status,
        review_reason=payload.review_reason,
        musicbrainz_id=payload.musicbrainz_id,
    )
    return ComposerAdminDetail.model_validate(detail)


@router.get(
    "/{composer_id}/biography",
    response_model=ComposerAdminDetail,
    summary="Biografía de un compositor",
    description="Devuelve el detalle del compositor con su biografía (summary, era, "
    "nationality, key_works, key_fact).",
)
async def get_composer_biography(
    composer_id: str,
    uc: GetComposerBiography = Depends(GetComposerBiographyDep),
) -> ComposerAdminDetail:
    return ComposerAdminDetail.model_validate(await uc.execute(composer_id))


@router.put(
    "/{composer_id}/biography",
    response_model=ComposerAdminDetail,
    summary="Actualizar biografía de un compositor",
    description="Crea o actualiza la biografía en composer_biographies. Solo se "
    "actualizan los campos enviados; envía el resto como null para dejarlos intactos.",
)
async def update_composer_biography(
    composer_id: str,
    payload: BiographyUpdateRequest,
    uc: UpdateComposerBiography = Depends(UpdateComposerBiographyDep),
) -> ComposerAdminDetail:
    detail = await uc.execute(
        composer_id,
        summary=payload.summary,
        era=payload.era,
        nationality=payload.nationality,
        key_works=payload.key_works,
        key_fact=payload.key_fact,
        references=payload.references,
    )
    return ComposerAdminDetail.model_validate(detail)


@router.delete(
    "/{composer_id}/identifiers/{identifier_id}",
    status_code=204,
    summary="Eliminar un identificador de un compositor",
    description="Elimina un identificador externo (composer_identifiers) de un compositor.",
)
async def delete_composer_identifier(
    composer_id: str,
    identifier_id: int,
    uc: DeleteComposerIdentifier = Depends(DeleteComposerIdentifierDep),
) -> None:
    await uc.execute(composer_id, identifier_id)


@router.get(
    "/{composer_id}/works",
    response_model=ComposerWorksResult,
    summary="Works de un compositor",
    description="Works asociadas al compositor (paginado). Sirve para revisar el impacto de una fusión.",
)
async def composer_works(
    composer_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: GetComposerWorks = Depends(GetComposerWorksDep),
) -> ComposerWorksResult:
    works, total = await uc.execute(composer_id, limit=limit, offset=offset)
    return ComposerWorksResult(
        items=[ComposerWorkRefRead.model_validate(w) for w in works],
        total=total,
    )


@router.post(
    "/{target_id}/merge",
    response_model=MergeComposersResultRead,
    summary="Fusionar compositores",
    description="Fusiona `source_ids` dentro de `target_id` de forma atómica. El target "
    "permanece activo; los source quedan `merged` con `merged_into = target`.",
)
async def merge_composers(
    target_id: str,
    payload: MergeComposersRequest,
    uc: MergeComposers = Depends(MergeComposersDep),
) -> MergeComposersResultRead:
    result = await uc.execute(target_id, payload.source_ids)
    return MergeComposersResultRead.model_validate(result)


@router.post(
    "/{composer_id}/review",
    response_model=ComposerAdminDetail,
    summary="Marcar revisión de un compositor",
    description="Marca un compositor como correct/false/pending. No borra ni modifica la identidad.",
)
async def review_composer(
    composer_id: str,
    payload: ComposerReviewRequest,
    uc: ReviewComposer = Depends(ReviewComposerDep),
) -> ComposerAdminDetail:
    detail = await uc.execute(composer_id, payload.review_status)
    return ComposerAdminDetail.model_validate(detail)


@router.post(
    "/{composer_id}/aliases",
    response_model=AliasRead,
    summary="Añadir alias a un compositor",
    description="Añade un alias (solo mejora el reconocimiento; no toca obras).",
)
async def add_alias(
    composer_id: str,
    payload: AddAliasRequest,
    uc: AddAlias = Depends(AddAliasDep),
) -> AliasRead:
    alias = await uc.execute(composer_id, payload.alias)
    return AliasRead(id=alias.id or 0, alias=alias.alias, normalized_alias=alias.normalized_alias)


@router.get(
    "/{composer_id}/aliases",
    response_model=list[AliasRead],
    summary="Listar alias de un compositor",
    description="Devuelve los alias de un compositor (con id, para mover/promover).",
)
async def list_aliases(
    composer_id: str,
    uc: ListAliases = Depends(ListAliasesDep),
) -> list[AliasRead]:
    aliases = await uc.execute(composer_id)
    return [AliasRead(id=a.id or 0, alias=a.alias, normalized_alias=a.normalized_alias) for a in aliases]


@router.post(
    "/{composer_id}/aliases/{alias_id}/move",
    response_model=MoveAliasResultRead,
    summary="Mover un alias a otro compositor",
    description="Mueve el alias (no se borra) y reasigna las obras que lo aportaron al destino.",
)
async def move_alias(
    composer_id: str,
    alias_id: int,
    payload: MoveAliasRequest,
    uc: MoveAlias = Depends(MoveAliasDep),
) -> MoveAliasResultRead:
    alias = await uc.execute(alias_id, payload.from_composer_id, payload.target_composer_id)
    return MoveAliasResultRead(
        alias=AliasRead(id=alias.id or 0, alias=alias.alias, normalized_alias=alias.normalized_alias)
    )


@router.post(
    "/{composer_id}/aliases/{alias_id}/promote",
    response_model=PromoteAliasResultRead,
    summary="Promover un alias a su propio Composer",
    description="Crea un Composer desde el alias y reasigna las obras que lo aportaron.",
)
async def promote_alias(
    composer_id: str,
    alias_id: int,
    uc: PromoteAlias = Depends(PromoteAliasDep),
) -> PromoteAliasResultRead:
    composer = await uc.execute(alias_id, composer_id)
    return PromoteAliasResultRead(composer_id=composer.id, name=composer.name)


@router.post(
    "/set-attribution",
    response_model=SetAttributionResultRead,
    summary="Convertir compositores a atribución",
    description="Las obras de los compositores guardan attribution_type + attribution_note "
    "(= nombre) y se les borra composer_id; los compositores se retiran.",
)
async def set_attribution(
    payload: SetAttributionRequest,
    uc: SetAttribution = Depends(SetAttributionDep),
) -> SetAttributionResultRead:
    affected = await uc.execute(payload.composer_ids, payload.attribution_type)
    return SetAttributionResultRead(works_affected=affected)
