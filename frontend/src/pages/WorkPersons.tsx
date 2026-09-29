import { useCallback, useEffect, useState } from 'react'

import { authHeaders, resolveToken } from '../auth'

// Listado de la relación obra ↔ persona (works_person_roles + persons + roles).
// Permite investigar qué persona está asociada a qué obra y en calidad de qué,
// y llegar a la ficha de la obra (SPA /t/works/:id) o de la persona (página curada
// /admin/maestros?id=…&mode=view).

const API = '/api/admin/work-persons'

interface Row {
  work_id: number
  work_title: string | null
  catalogue: string | null
  person_id: string | null
  person_name: string | null
  role_name: string | null
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { ...authHeaders() } })
  if (!response.ok) throw new Error(`Error ${response.status}`)
  return (await response.json()) as T
}

function tokenParam(): string {
  const token = resolveToken()
  return token ? `?token=${encodeURIComponent(token)}` : ''
}

export default function WorkPersons() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [missing, setMissing] = useState(false)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const limit = 50

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
      if (q.trim()) params.set('q', q.trim())
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
  }, [q, role, missing, offset])

  useEffect(() => {
    void load()
  }, [load])

  const token = tokenParam()

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
          void load()
        }}
      >
        <div className="row">
          <input
            className="grow"
            placeholder="Buscar por obra, catálogo o persona"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <input
            placeholder="Rol exacto (composer, arranger…)"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          />
          <label style={{ margin: 0 }}>
            <input type="checkbox" checked={missing} onChange={(e) => setMissing(e.target.checked)} />{' '}
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
              <th>Obra</th>
              <th>Persona</th>
              <th>Concepto / rol</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.work_id}-${r.person_id ?? 'none'}-${r.role_name ?? 'none'}-${i}`}>
                <td>
                  {r.work_title ?? `Obra #${r.work_id}`}
                  {r.catalogue ? <span className="muted"> · {r.catalogue}</span> : null}
                </td>
                <td>{r.person_name ?? <em className="muted">— sin persona —</em>}</td>
                <td>{r.role_name ?? <em className="muted">— sin rol —</em>}</td>
                <td className="tools">
                  <a href={`/admin/t/works/${r.work_id}${token}`}>→ Obra</a>
                  {r.person_id ? (
                    <a href={`/admin/maestros?id=${encodeURIComponent(r.person_id)}&mode=view${token.replace('?', '&')}`}>
                      → Persona
                    </a>
                  ) : null}
                </td>
              </tr>
            ))}
            {rows.length === 0 && !loading ? (
              <tr>
                <td colSpan={4} className="empty">
                  Sin resultados.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        <div className="pager">
          <button className="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
            ←
          </button>
          <span>
            {offset + 1}–{Math.min(offset + limit, total)} de {total}
          </span>
          <button
            className="ghost"
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
          >
            →
          </button>
        </div>
      </div>
    </section>
  )
}
