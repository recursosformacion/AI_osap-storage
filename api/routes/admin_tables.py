from __future__ import annotations

from typing import Any

from application.use_cases.table_crud import TableCrud
from fastapi import APIRouter, Body, Depends, Query

from api.dependencies import TableCrudDep
from api.schemas import TableCrudRow, TableCrudRows, TableCrudTables

router = APIRouter(
    prefix="/api/admin/tables",
    tags=["admin-crud"],
)


@router.get(
    "",
    response_model=TableCrudTables,
    summary="Tablas disponibles",
    description="Lista las tablas expuestas al CRUD genérico.",
)
async def list_tables(uc: TableCrud = Depends(TableCrudDep)) -> TableCrudTables:
    return TableCrudTables(tables=await uc.list_tables())


@router.get(
    "/{table}",
    response_model=TableCrudRows,
    summary="Leer filas",
    description="Lee filas de una tabla (paginado).",
)
async def read_rows(
    table: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: TableCrud = Depends(TableCrudDep),
) -> TableCrudRows:
    rows = await uc.read(table, limit=limit, offset=offset)
    return TableCrudRows(table=table, total=len(rows), rows=rows)


@router.get(
    "/{table}/{pk_value}",
    response_model=TableCrudRow,
    summary="Leer una fila",
    description="Lee una fila por su clave primaria.",
)
async def read_one(
    table: str,
    pk_value: Any,
    uc: TableCrud = Depends(TableCrudDep),
) -> TableCrudRow:
    row = await uc.read_one(table, pk_value)
    if row is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="fila no encontrada")
    return TableCrudRow(table=table, row=row)


@router.post(
    "/{table}",
    response_model=TableCrudRow,
    summary="Crear fila",
    description="Crea una fila en la tabla con los campos dados (se validan contra las columnas reales).",
)
async def create_row(
    table: str,
    payload: dict[str, Any] = Body(...),
    uc: TableCrud = Depends(TableCrudDep),
) -> TableCrudRow:
    return TableCrudRow(table=table, row=await uc.create(table, payload))


@router.put(
    "/{table}/{pk_value}",
    response_model=TableCrudRow,
    summary="Actualizar fila",
    description="Actualiza una fila por su clave primaria.",
)
async def update_row(
    table: str,
    pk_value: Any,
    payload: dict[str, Any] = Body(...),
    uc: TableCrud = Depends(TableCrudDep),
) -> TableCrudRow:
    row = await uc.update(table, pk_value, payload)
    if row is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="fila no encontrada")
    return TableCrudRow(table=table, row=row)


@router.delete(
    "/{table}/{pk_value}",
    response_model=TableCrudRow,
    summary="Borrar fila",
    description="Borra una fila por su clave primaria.",
)
async def delete_row(
    table: str,
    pk_value: Any,
    uc: TableCrud = Depends(TableCrudDep),
) -> TableCrudRow:
    deleted = await uc.delete(table, pk_value)
    if deleted == 0:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="fila no encontrada")
    return TableCrudRow(table=table, row={})
