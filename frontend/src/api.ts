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

export function getRows(
  table: string,
  limit: number,
  offset: number,
  q?: string,
  filter?: string,
): Promise<RowsResponse> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q) query.set('q', q)
  if (filter) query.set('filter', filter)
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

const REP_API = '/api/admin/representations'

async function requestUrl<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
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

export interface RepresentationListItem {
  id: number
  works_id: number
  origin: string
  origin_id?: string | null
  type: string
  license: string
  source_name?: string | null
  resources: number
  editors: number
}

export interface RepresentationListFilter {
  origin?: string
  license?: string
  works_id?: string
  q?: string
  limit?: number
  offset?: number
}

export interface RepresentationResource {
  id: number
  type: string
  name: string
  relative_path?: string | null
  status: string
  file_id?: number | null
  url?: string | null
  archive_id?: number | null
}

export interface RepresentationEditor {
  id: number
  person_id?: string | null
  role_id?: number | null
  name?: string | null
  person_name?: string | null
}

export interface RepresentationDetail {
  id: number
  works_id: number
  origin: string
  origin_id?: string | null
  cpdlno?: number | null
  type: string
  license: string
  source_name?: string | null
  work?: { id?: number | null; title?: string | null; origin?: string | null } | null
  resources: RepresentationResource[]
  editors: RepresentationEditor[]
}

export interface RepresentationPayload {
  works_id: number
  origin: string
  origin_id?: string
  cpdlno?: number
  type?: string
  license?: string
  source_name?: string
}

export function listRepresentations(
  filter: RepresentationListFilter,
): Promise<{ items: RepresentationListItem[]; total: number }> {
  const query = new URLSearchParams()
  if (filter.origin) query.set('origin', filter.origin)
  if (filter.license) query.set('license', filter.license)
  if (filter.works_id) query.set('works_id', filter.works_id)
  if (filter.q) query.set('q', filter.q)
  query.set('limit', String(filter.limit ?? 25))
  query.set('offset', String(filter.offset ?? 0))
  return requestUrl(`${REP_API}?${query.toString()}`)
}

export function getRepresentation(id: number): Promise<RepresentationDetail> {
  return requestUrl(`${REP_API}/${id}`)
}

export function createRepresentation(payload: RepresentationPayload): Promise<RepresentationDetail> {
  return requestUrl(REP_API, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateRepresentation(
  id: number,
  payload: RepresentationPayload,
): Promise<RepresentationDetail> {
  return requestUrl(`${REP_API}/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteRepresentation(id: number): Promise<{ deleted: number }> {
  return requestUrl(`${REP_API}/${id}`, { method: 'DELETE' })
}

const RES_API = '/api/admin/resources'

export interface ResourceListItem {
  id: number
  work_id: number
  representation_id?: number | null
  type: string
  name: string
  relative_path?: string | null
  status: string
  file_id?: number | null
  url?: string | null
  archive_id?: number | null
}

export interface ResourceDetail extends ResourceListItem {
  work?: { id?: number | null; title?: string | null; origin?: string | null } | null
  representation?: {
    id?: number | null
    origin?: string | null
    origin_id?: string | null
    type?: string | null
    license?: string | null
  } | null
}

export interface ResourceFilter {
  work_id?: string
  representation_id?: string
  type?: string
  status?: string
  has_url?: string
  q?: string
  limit?: number
  offset?: number
}

export interface ResourcePayload {
  work_id: number
  representation_id?: number
  type?: string
  name?: string
  relative_path?: string
  status?: string
  file_id?: number
  url?: string
  archive_id?: number
}

export function listResources(
  filter: ResourceFilter,
): Promise<{ items: ResourceListItem[]; total: number }> {
  const query = new URLSearchParams()
  if (filter.work_id) query.set('work_id', filter.work_id)
  if (filter.representation_id) query.set('representation_id', filter.representation_id)
  if (filter.type) query.set('type', filter.type)
  if (filter.status) query.set('status', filter.status)
  if (filter.has_url) query.set('has_url', filter.has_url)
  if (filter.q) query.set('q', filter.q)
  query.set('limit', String(filter.limit ?? 25))
  query.set('offset', String(filter.offset ?? 0))
  return requestUrl(`${RES_API}?${query.toString()}`)
}

export function getResource(id: number): Promise<ResourceDetail> {
  return requestUrl(`${RES_API}/${id}`)
}

export function createResource(payload: ResourcePayload): Promise<ResourceDetail> {
  return requestUrl(RES_API, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateResource(id: number, payload: ResourcePayload): Promise<ResourceDetail> {
  return requestUrl(`${RES_API}/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function deleteResource(id: number): Promise<{ deleted: number }> {
  return requestUrl(`${RES_API}/${id}`, { method: 'DELETE' })
}
