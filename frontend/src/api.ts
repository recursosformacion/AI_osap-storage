export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }
export type Row = Record<string, JsonValue | undefined>

export interface SchemaColumn {
  name: string
  type: string
  nullable: boolean
  key: string
  default: JsonValue | null
  extra: string
}

export interface SchemaRelation {
  column: string
  ref_table: string
  ref_column: string
  name: string
}

export interface TableSchema {
  table: string
  pk: string
  columns: SchemaColumn[]
  relations: SchemaRelation[]
}

export interface TableListResponse {
  tables: string[]
}

export interface RowsResponse {
  table: string
  total: number
  rows: Row[]
}

export interface RowResponse {
  table: string
  row: Row
}

export class ApiRequestError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

const API_ROOT = '/api/admin/tables'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let message = `La API respondió con el estado ${response.status}.`
    try {
      const payload = (await response.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string') message = payload.detail
      else if (payload.detail) message = JSON.stringify(payload.detail)
    } catch {
      // Keep the status message when the response is not JSON.
    }
    throw new ApiRequestError(message, response.status)
  }

  return (await response.json()) as T
}

export function listTables(): Promise<TableListResponse> {
  return request<TableListResponse>('')
}

export function getSchema(table: string): Promise<TableSchema> {
  return request<TableSchema>(`/${encodeURIComponent(table)}/schema`)
}

export function getRows(table: string, limit: number, offset: number): Promise<RowsResponse> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return request<RowsResponse>(`/${encodeURIComponent(table)}?${query.toString()}`)
}

export function getRow(table: string, pk: string): Promise<RowResponse> {
  return request<RowResponse>(`/${encodeURIComponent(table)}/${encodeURIComponent(pk)}`)
}

export function createRow(table: string, row: Row): Promise<RowResponse> {
  return request<RowResponse>(`/${encodeURIComponent(table)}`, {
    method: 'POST',
    body: JSON.stringify(row),
  })
}

export function updateRow(table: string, pk: string, row: Row): Promise<RowResponse> {
  return request<RowResponse>(`/${encodeURIComponent(table)}/${encodeURIComponent(pk)}`, {
    method: 'PUT',
    body: JSON.stringify(row),
  })
}

export function deleteRow(table: string, pk: string): Promise<RowResponse> {
  return request<RowResponse>(`/${encodeURIComponent(table)}/${encodeURIComponent(pk)}`, {
    method: 'DELETE',
  })
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'No se pudo completar la operación.'
}
