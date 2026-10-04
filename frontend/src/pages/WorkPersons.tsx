import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { authHeaders } from '../auth'

// Listado de la relación obra ↔ persona (works_person_roles + persons + roles).
// Permite investigar qué persona está asociada a qué obra y en calidad de qué, y llegar a la
// ficha de la obra (/t/works/:id) o de la persona (/t/persons/:id) con navegación interna
// (react-router), de modo que el token de sessionStorage sobreviva.
//
// Columnas: Obra · Persona · Rol · Autoría (works_attr_type) · Origen (works_origin) · Acciones.
// Cabeceras ordenables (asc/desc) y paginación que recarga de verdad cada página.

const API = '/api/admin/work-persons'

type SortKey = 'work' | 'person' | 'role' | 'attribution' | 'origin'
type Direction = 'asc' | 'desc'

const DEFAULT_DIRECTION: Record<SortKey, Direction> = {
  work: 'desc',
  person: 'asc',
  role: 'asc',
  attribution: 'asc',
  origin: 'asc',
}

interface Row {
  work_id: number
  work_title: string | null
  catalogue: string | null
  person_id: string | null
  person_name: string | null
  role_name: string | null
  attribution: string | null
  origin: string | null
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { ...authHeaders() } })
  if (!response.ok) throw new Error(`Error ${response.status}`)
  return (await response.json()) as T
}

function SortHeader({
  label,
  sortKey,
  sort,
  direction,
  onSort,
}: {
  label: string
  sortKey: SortKey
  sort: SortKey
  direction: Direction
  onSort: (key: SortKey) => void
}) {
  const active = sort === sortKey
  const ariaSort = active ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'
  return (
    <th scope="col" aria-sort={ariaSort}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        style={{
          background: 'transparent',
          border: 0,
          color: 'inherit',
          font: 'inherit',
          letterSpacing: 'inherit',
          textTransform: 'inherit',
          cursor: 'pointer',
          padding: 0,
        }}
        title={`Ordenar por ${label}`}
      >
        {label}
        {active ? (direction === 'asc' ? ' ↑' : ' ↓') : ''}
      </button>
    </th>
  )
}

export default function WorkPersons() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [roleOptions, setRoleOptions] = useState<{ value: string; label: string }[]>([])
  const [q, setQ] = useState('')
  const [appliedQ, setAppliedQ] = useState('')
  const [role, setRole] = useState('')
  const [missing, setMissing] = useState(false)
  const [sort, setSort] = useState<SortKey>('work')
  const [direction, setDirection] = useState<Direction>('desc')
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const limit = 50

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
        sort,
        direction,
      })
      if (appliedQ) params.set('q', appliedQ)
      if (role.trim()) params.set('role', role.trim())
      if (missing) params.set('missing', 'true')
      const data = await getJson<{ items: Row[]; total: number }>(`${API}?${params}`)
      setRows(data.items)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cargar')
    } finally {
      setLoading(false)
    }
  }, [appliedQ, role, missing, offset, sort, direction])

  useEffect(() => {
    void load()
  }, [load])

  // Roles disponibles (distinct de la tabla `roles`) para el desplegable.
  useEffect(() => {
    void (async () => {
      try {
        const data = await getJson<{ options: { value: number; label: string }[] }>(
          '/api/admin/work-persons/roles',
        )
        setRoleOptions(data.options.map((o) => ({ value: String(o.value), label: o.label })))
      } catch {
        // Sin desplegable, el filtro queda vacío (no bloquea el listado).
      }
    })()
  }, [])

  function onSort(key: SortKey) {
    setOffset(0)
    if (key === sort) {
      setDirection((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(key)
      setDirection(DEFAULT_DIRECTION[key])
    }
  }

  const pageEnd = Math.min(offset + rows.length, total)

  return (
    <section>
      <h1>Obras → Personas</h1>
      <p className="muted">
        Relación canónica <code>works_person_roles</code>: obra, persona y rol (concepto).
      </p>

      <form
        className="card"
        onSubmit={(e) => {
          e.preventDefault()
          setOffset(0)
          setAppliedQ(q.trim())
        }}
      >
        <div className="row">
          <input
            className="grow"
            placeholder="Buscar por obra, catálogo o persona"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select
            value={role}
            onChange={(e) => {
              setOffset(0)
              setRole(e.target.value)
            }}
          >
            <option value="">(todos los roles)</option>
            {roleOptions.map((o) => (
              <option key={o.value} value={o.label}>
                {o.label}
              </option>
            ))}
          </select>
          <label style={{ margin: 0 }}>
            <input
              type="checkbox"
              checked={missing}
              onChange={(e) => {
                setOffset(0)
                setMissing(e.target.checked)
              }}
            />{' '}
            Solo obras sin persona
          </label>
          <button type="submit">Buscar</button>
        </div>
      </form>

      {error && <div className="card">{error}</div>}
      {loading && <div className="card">Cargando…</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <SortHeader
                label="Obra"
                sortKey="work"
                sort={sort}
                direction={direction}
                onSort={onSort}
              />
              <SortHeader
                label="Persona"
                sortKey="person"
                sort={sort}
                direction={direction}
                onSort={onSort}
              />
              <SortHeader
                label="Concepto / rol"
                sortKey="role"
                sort={sort}
                direction={direction}
                onSort={onSort}
              />
              <SortHeader
                label="Autoría"
                sortKey="attribution"
                sort={sort}
                direction={direction}
                onSort={onSort}
              />
              <SortHeader
                label="Origen"
                sortKey="origin"
                sort={sort}
                direction={direction}
                onSort={onSort}
              />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.work_id}-${r.person_id ?? 'none'}-${r.role_name ?? 'none'}-${i}`}>
                <td>
                  <Link
                    to={`/t/works/${r.work_id}`}
                    className="text-osap-accent hover:underline"
                    title="Abrir la ficha de la obra"
                  >
                    {r.work_title ?? `Obra #${r.work_id}`}
                  </Link>
                  {r.catalogue ? <span className="muted"> · {r.catalogue}</span> : null}
                </td>
                <td>
                  {r.person_id ? (
                    <Link
                      to={`/t/persons/${encodeURIComponent(r.person_id)}`}
                      className="text-osap-accent hover:underline"
                      title="Abrir la ficha de la persona"
                    >
                      {r.person_name ?? r.person_id}
                    </Link>
                  ) : (
                    <em className="muted">— sin persona —</em>
                  )}
                </td>
                <td>{r.role_name ?? <em className="muted">— sin rol —</em>}</td>
                <td>{r.attribution ?? <span className="muted">—</span>}</td>
                <td>{r.origin ?? <span className="muted">—</span>}</td>
              </tr>
            ))}
            {rows.length === 0 && !loading ? (
              <tr>
                <td colSpan={5} className="empty">
                  Sin resultados.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        <div className="pager">
          <button
            type="button"
            className="ghost"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            ←
          </button>
          <span>
            {total === 0 ? '0' : `${offset + 1}–${pageEnd}`} de {total}
          </span>
          <button
            type="button"
            className="ghost"
            disabled={pageEnd >= total}
            onClick={() => setOffset(offset + limit)}
          >
            →
          </button>
        </div>
      </div>
    </section>
  )
}
