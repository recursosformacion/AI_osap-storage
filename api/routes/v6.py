"""API V6 de lectura: Work → Resource → File.

Aditiva sobre /api/v1 mientras se prepara el corte. No expone claves físicas ni
StorageLocation; los Files se devuelven sin `storage_key`.
"""

from __future__ import annotations

import json
from typing import Any

from application.use_cases.get_download_url import GetDownloadUrl
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from infrastructure.config import Settings
from infrastructure.db.connection import Database

from api.dependencies import GetDownloadUrlDep, get_db, get_settings
from api.schemas_v6 import (
    V6AccessRead,
    V6AccessRequest,
    V6FileCreate,
    V6FileRead,
    V6IndexPage,
    V6IndexResource,
    V6IndexWork,
    V6ReferenceRead,
    V6ReferenceResource,
    V6ResourceCreate,
    V6ResourceDetail,
    V6ResourceRead,
    V6ResourceUpdate,
    V6WorkDetail,
    V6WorkSummary,
    V6WorkUpdate,
)

router = APIRouter(prefix="/api/v6", tags=["v6"])


def _metadata(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _work(row: dict[str, Any]) -> V6WorkSummary:
    return V6WorkSummary(
        id=row["id"],
        title=row.get("works_title"),
        song_name=row.get("works_song_name"),
        catalogue=row.get("works_catalogue"),
        musical_key=row.get("works_musical_key"),
        resource_count=int(row.get("resource_count") or 0),
    )


def _resource(row: dict[str, Any]) -> V6ResourceRead:
    return V6ResourceRead(
        id=row["id"],
        work_id=row["work_id"],
        kind=row.get("kind") or "score",
        title=row.get("title"),
        source_system=row.get("source_system"),
        external_id=row.get("external_id"),
        external_url=row.get("external_url"),
        license=row.get("license"),
        rights_holder=row.get("rights_holder"),
        is_reference=bool(row.get("is_reference")),
        visibility=row.get("visibility") or "public",
        metadata=_metadata(row.get("metadata_json")),
    )


def _require_actor(actor: str | None) -> str:
    value = (actor or "").strip()
    if not value:
        raise HTTPException(status_code=401, detail="Actor required")
    return value


async def _require_composer(
    cur: Any, work_id: int, actor_persons: str | None
) -> None:
    """Exige que una de las identidades Person del actor sea compositora de la Work."""
    person_ids = {part.strip() for part in (actor_persons or "").split(",") if part.strip()}
    if not person_ids:
        raise HTTPException(status_code=403, detail="Composer identity required")
    await cur.execute(
        "SELECT works_person_roles_person_id AS person_id FROM works_person_roles "
        "WHERE works_person_roles_work_id = %s AND works_person_roles_role_id = 1",
        (work_id,),
    )
    composers = {str(row["person_id"]) for row in await cur.fetchall()}
    if not (person_ids & composers):
        raise HTTPException(status_code=403, detail="Only the Work composer can edit it")


def _file(row: dict[str, Any]) -> V6FileRead:
    return V6FileRead(
        id=row["id"],
        name=row["name"],
        mime_type=row.get("mime_type"),
        size_bytes=row.get("size_bytes"),
        status=row.get("status") or "registered",
    )


@router.get("/works", response_model=list[V6WorkSummary], summary="Buscar Works V6")
async def list_works(
    q: str = Query(default="", max_length=200),
    composer: str = Query(default="", max_length=200),
    catalogue: str = Query(default="", max_length=200),
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Database = Depends(get_db),
) -> list[V6WorkSummary]:
    like = f"%{q.strip()}%"
    composer_like = f"%{composer.strip()}%"
    catalogue_like = f"%{catalogue.strip()}%"
    sql = """
        SELECT w.id, w.works_title, w.works_song_name, w.works_catalogue,
               w.works_musical_key,
               (SELECT COUNT(*) FROM resources r WHERE r.work_id = w.id) AS resource_count
        FROM works w
        WHERE EXISTS (SELECT 1 FROM resources r WHERE r.work_id = w.id)
          AND (%s = '' OR w.works_title LIKE %s OR w.works_song_name LIKE %s)
          AND (%s = '' OR w.works_catalogue LIKE %s)
          AND (%s = '' OR EXISTS (
                SELECT 1 FROM works_person_roles wpr
                JOIN persons p ON p.persons_id = wpr.works_person_roles_person_id
                WHERE wpr.works_person_roles_work_id = w.id
                  AND wpr.works_person_roles_role_id = 1
                  AND p.persons_name LIKE %s))
          AND w.id > %s
        ORDER BY w.id
        LIMIT %s
    """
    params = (
        q.strip(),
        like,
        like,
        catalogue.strip(),
        catalogue_like,
        composer.strip(),
        composer_like,
        cursor,
        limit,
    )
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    return [_work(row) for row in rows]


@router.post(
    "/works/{work_id}/resources",
    response_model=V6ResourceRead,
    status_code=201,
    summary="Añadir Resource a una Work",
)
async def create_resource(
    work_id: int,
    body: V6ResourceCreate,
    actor: str | None = Header(default=None, alias="X-Actor-User-Id"),
    db: Database = Depends(get_db),
) -> V6ResourceRead:
    """Alta de Resource desde la fachada de servicio.

    El actor llega en una cabecera de confianza puesta por OSAP-API tras validar
    la sesión; en producción la ruta está detrás de la autenticación de servicio.
    La comprobación de que el actor es compositor de la Work queda pendiente.
    """
    actor = _require_actor(actor)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id FROM works WHERE id = %s", (work_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Work not found")
        await cur.execute(
            "INSERT INTO resources (work_id, kind, title, source_system, external_id, "
            "external_url, license, rights_holder, is_reference, visibility, "
            "metadata_json, created_by, legacy_kind, legacy_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'public', %s, %s, NULL, NULL)",
            (
                work_id,
                body.kind,
                body.title,
                body.source_system,
                body.external_id,
                body.external_url,
                body.license,
                body.rights_holder,
                int(body.kind == "reference"),
                json.dumps(body.metadata, ensure_ascii=False) if body.metadata else None,
                actor,
            ),
        )
        resource_id = cur.lastrowid
        await cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
        row = await cur.fetchone()
    return _resource(row)


@router.patch(
    "/resources/{resource_id}",
    response_model=V6ResourceRead,
    summary="Modificar Resource",
)
async def update_resource(
    resource_id: int,
    body: V6ResourceUpdate,
    actor: str | None = Header(default=None, alias="X-Actor-User-Id"),
    db: Database = Depends(get_db),
) -> V6ResourceRead:
    """Solo el creador del Resource puede modificarlo.

    Los Resources importados (`created_by` nulo) no se editan por esta ruta; su
    gestión corresponde al proceso de la fuente.
    """
    actor = _require_actor(actor)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes")
    if "metadata" in changes and changes["metadata"] is not None:
        changes["metadata"] = json.dumps(changes["metadata"], ensure_ascii=False)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        if str(row.get("created_by") or "") != actor:
            raise HTTPException(status_code=403, detail="Only the creator can edit this Resource")
        assignments = ", ".join(f"{column} = %s" for column in changes)
        await cur.execute(
            f"UPDATE resources SET {assignments} WHERE id = %s",
            (*changes.values(), resource_id),
        )
        await cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
        row = await cur.fetchone()
    return _resource(row)


@router.get(
    "/index/works",
    response_model=V6IndexPage,
    summary="Feed de índice V6 (IDs públicos estables)",
)
async def index_works(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: Database = Depends(get_db),
) -> V6IndexPage:
    """Feed canónico para reconstruir el índice sin cambiar IDs ni slugs.

    `work_id` es `index-<works.id>`; el título es `works_title`, del que el
    consumidor deriva el slug con la misma función que la web.
    """
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            """
            SELECT w.id, w.works_title, w.works_song_name, w.works_catalogue,
                   (SELECT p.persons_name FROM works_person_roles wpr
                      JOIN persons p ON p.persons_id = wpr.works_person_roles_person_id
                     WHERE wpr.works_person_roles_work_id = w.id
                       AND wpr.works_person_roles_role_id = 1
                     ORDER BY wpr.works_person_roles_order, wpr.works_person_roles_id
                     LIMIT 1) AS composer
            FROM works w
            WHERE EXISTS (SELECT 1 FROM resources r WHERE r.work_id = w.id)
              AND w.id > %s
            ORDER BY w.id
            LIMIT %s
            """,
            (cursor, limit),
        )
        work_rows = await cur.fetchall()
        if not work_rows:
            return V6IndexPage(items=[], next_cursor=None)
        ids = [row["id"] for row in work_rows]
        placeholders = ",".join(["%s"] * len(ids))
        await cur.execute(
            "SELECT id, work_id, kind, source_system, external_id, external_url "
            f"FROM resources WHERE work_id IN ({placeholders}) ORDER BY id",
            ids,
        )
        resource_rows = await cur.fetchall()
        files_by_resource: dict[int, list[int]] = {}
        if resource_rows:
            resource_ids = [row["id"] for row in resource_rows]
            resource_placeholders = ",".join(["%s"] * len(resource_ids))
            await cur.execute(
                "SELECT id, resource_id FROM files "
                f"WHERE resource_id IN ({resource_placeholders}) ORDER BY id",
                resource_ids,
            )
            for row in await cur.fetchall():
                files_by_resource.setdefault(row["resource_id"], []).append(row["id"])

    resources_by_work: dict[int, list[V6IndexResource]] = {}
    for row in resource_rows:
        resources_by_work.setdefault(row["work_id"], []).append(
            V6IndexResource(
                id=row["id"],
                kind=row.get("kind") or "score",
                source_system=row.get("source_system"),
                external_id=row.get("external_id"),
                external_url=row.get("external_url"),
                file_ids=files_by_resource.get(row["id"], []),
            )
        )
    items = [
        V6IndexWork(
            work_id=f"index-{row['id']}",
            title=row.get("works_title") or "",
            song_name=row.get("works_song_name"),
            catalogue=row.get("works_catalogue"),
            composer=row.get("composer"),
            resources=resources_by_work.get(row["id"], []),
        )
        for row in work_rows
    ]
    next_cursor = work_rows[-1]["id"] if len(work_rows) == limit else None
    return V6IndexPage(items=items, next_cursor=next_cursor)


@router.patch("/works/{work_id}", response_model=V6WorkSummary, summary="Modificar Work")
async def update_work(
    work_id: int,
    body: V6WorkUpdate,
    actor_persons: str | None = Header(default=None, alias="X-Actor-Person-Ids"),
    db: Database = Depends(get_db),
) -> V6WorkSummary:
    """Solo el compositor puede editar metadatos de Work.

    `works_title`/`works_song_name` no se exponen aquí: cambiarlos altera el slug
    público y exige tabla de correspondencia + 301 antes de reindexar.
    """
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes")
    column_by_field = {
        "subtitle": "works_subtitle",
        "catalogue": "works_catalogue",
        "musical_key": "works_musical_key",
        "description": "works_description",
        "attribution_note": "works_attribution_note",
    }
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id FROM works WHERE id = %s", (work_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Work not found")
        await _require_composer(cur, work_id, actor_persons)
        assignments = ", ".join(column_by_field[field] + " = %s" for field in changes)
        await cur.execute(
            f"UPDATE works SET {assignments} WHERE id = %s",
            (*changes.values(), work_id),
        )
        await cur.execute(
            "SELECT w.id, w.works_title, w.works_song_name, w.works_catalogue, "
            "w.works_musical_key, "
            "(SELECT COUNT(*) FROM resources r WHERE r.work_id = w.id) AS resource_count "
            "FROM works w WHERE w.id = %s",
            (work_id,),
        )
        row = await cur.fetchone()
    return _work(row)


@router.put(
    "/works/{work_id}/reference-resource",
    response_model=V6ReferenceRead,
    summary="Asignar o retirar el Resource de referencia",
)
async def set_reference_resource(
    work_id: int,
    body: V6ReferenceResource,
    actor_persons: str | None = Header(default=None, alias="X-Actor-Person-Ids"),
    db: Database = Depends(get_db),
) -> V6ReferenceRead:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id FROM works WHERE id = %s", (work_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Work not found")
        await _require_composer(cur, work_id, actor_persons)
        if body.resource_id is not None:
            await cur.execute(
                "SELECT id FROM resources WHERE id = %s AND work_id = %s",
                (body.resource_id, work_id),
            )
            if await cur.fetchone() is None:
                raise HTTPException(
                    status_code=422, detail="Resource does not belong to this Work"
                )
        await cur.execute(
            "UPDATE works SET reference_resource_id = %s WHERE id = %s",
            (body.resource_id, work_id),
        )
    return V6ReferenceRead(work_id=work_id, reference_resource_id=body.resource_id)


@router.get("/works/{work_id}", response_model=V6WorkDetail, summary="Work y Resources")
async def get_work(work_id: int, db: Database = Depends(get_db)) -> V6WorkDetail:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            """
            SELECT w.id, w.works_title, w.works_song_name, w.works_catalogue,
                   w.works_musical_key,
                   (SELECT COUNT(*) FROM resources r WHERE r.work_id = w.id) AS resource_count
            FROM works w WHERE w.id = %s
            """,
            (work_id,),
        )
        work_row = await cur.fetchone()
        if work_row is None:
            raise HTTPException(status_code=404, detail="Work not found")
        await cur.execute(
            "SELECT * FROM resources WHERE work_id = %s ORDER BY id",
            (work_id,),
        )
        resource_rows = await cur.fetchall()
    return V6WorkDetail(
        work=_work(work_row),
        resources=[_resource(row) for row in resource_rows],
    )


@router.get(
    "/resources/{resource_id}",
    response_model=V6ResourceDetail,
    summary="Resource y Files",
)
async def get_resource(
    resource_id: int, db: Database = Depends(get_db)
) -> V6ResourceDetail:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        await cur.execute(
            "SELECT id, name, mime_type, size_bytes, status FROM files "
            "WHERE resource_id = %s ORDER BY id",
            (resource_id,),
        )
        files = await cur.fetchall()
    resource = _resource(row)
    return V6ResourceDetail(
        **resource.model_dump(), files=[_file(item) for item in files]
    )


@router.post(
    "/resources/{resource_id}/files",
    response_model=V6FileRead,
    status_code=201,
    summary="Registrar File en un Resource",
)
async def create_file(
    resource_id: int,
    body: V6FileCreate,
    actor: str | None = Header(default=None, alias="X-Actor-User-Id"),
    db: Database = Depends(get_db),
) -> V6FileRead:
    """Registro de File por el creador del Resource.

    `storage_key` procede del proceso de carga de confianza; no se acepta de un
    cliente público (la ruta va detrás de la autenticación de servicio).
    """
    actor = _require_actor(actor)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, created_by FROM resources WHERE id = %s", (resource_id,)
        )
        resource = await cur.fetchone()
        if resource is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        if str(resource.get("created_by") or "") != actor:
            raise HTTPException(status_code=403, detail="Only the creator can add Files")
        await cur.execute(
            "INSERT INTO files (sha256, name, mime_type, size_bytes, status, "
            "storage_key, resource_id) VALUES (NULL, %s, %s, %s, 'registered', %s, %s)",
            (body.name, body.mime_type, body.size_bytes, body.storage_key, resource_id),
        )
        file_id = cur.lastrowid
        await cur.execute(
            "SELECT id, name, mime_type, size_bytes, status FROM files WHERE id = %s",
            (file_id,),
        )
        row = await cur.fetchone()
    return _file(row)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    actor: str | None = Header(default=None, alias="X-Actor-User-Id"),
    db: Database = Depends(get_db),
) -> Response:
    """Retirada lógica: el File deja de servirse, sin borrar el objeto R2."""
    actor = _require_actor(actor)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT f.id, r.created_by FROM files f "
            "LEFT JOIN resources r ON r.id = f.resource_id WHERE f.id = %s",
            (file_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="File not found")
        if str(row.get("created_by") or "") != actor:
            raise HTTPException(status_code=403, detail="Only the creator can delete Files")
        await cur.execute(
            "UPDATE files SET status = 'deleted' WHERE id = %s", (file_id,)
        )
    return Response(status_code=204)


@router.post(
    "/files/{file_id}/access",
    response_model=V6AccessRead,
    summary="Acceso al File",
)
async def file_access(
    file_id: int,
    body: V6AccessRequest,
    uc: GetDownloadUrl = Depends(GetDownloadUrlDep),
    settings: Settings = Depends(get_settings),
) -> V6AccessRead:
    """Resuelve el acceso sin aceptar provider_id ni object_key del cliente."""
    target = await uc.execute(file_id, None)
    url = target.native_url or (
        f"{settings.public_base_url.rstrip('/')}"
        f"/api/v1/files/{file_id}/content?provider_id={target.provider.id}"
    )
    return V6AccessRead(url=url, action=body.action)


@router.get("/files/{file_id}", response_model=V6FileRead, summary="File público")
async def get_file(file_id: int, db: Database = Depends(get_db)) -> V6FileRead:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, name, mime_type, size_bytes, status FROM files WHERE id = %s",
            (file_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")
    return _file(row)
