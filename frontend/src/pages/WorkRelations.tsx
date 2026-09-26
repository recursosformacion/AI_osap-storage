import { useCallback, useEffect, useState } from 'react'

// Editor de las tablas de enlace de una obra: cada relación es una FILA con sus selects
// (persona + rol, o el valor de la tabla) y una "X" para borrarla; debajo hay una fila en
// blanco para añadir. Cambiar un select equivale a modificar (se borra la relación antigua
// y se crea la nueva). Es la vía de mantenimiento de las tablas de enlaces.

const API = '/api/admin/works'

interface RelItem {
  ref_id?: string | number
  label?: string | null
  role_id?: number | string | null
  role_name?: string | null
  quantity?: number | null
  context?: string | null
}

interface Option {
  value: string | number
  label?: string | null
  role_id?: number | string | null
  role_name?: string | null
}

const PANELS: { key: string; title: string; hint: string }[] = [
  { key: 'person_roles', title: 'Personas y rol', hint: 'compositor, arreglista, intérprete…' },
  { key: 'genres', title: 'Géneros', hint: '' },
  { key: 'instruments', title: 'Instrumentos', hint: '' },
  { key: 'languages', title: 'Idiomas', hint: '' },
  { key: 'voices', title: 'Voces', hint: '' },
  { key: 'ensembles', title: 'Conjuntos', hint: '' },
]

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Error ${response.status}`)
  return (await response.json()) as T
}

async function sendJson(url: string, method: 'POST' | 'DELETE', body: unknown): Promise<void> {
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = `Error ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string') detail = payload.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
}

interface Props {
  workId: string
  editing: boolean
}

export default function WorkRelations({ workId, editing }: Props) {
  const [relations, setRelations] = useState<Record<string, RelItem[]>>({})
  const [options, setOptions] = useState<Record<string, Option[]>>({})
  const [draft, setDraft] = useState<Record<string, { value: string; role: string }>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      const data = await getJson<{ relations: Record<string, RelItem[]> }>(
        `${API}/${encodeURIComponent(workId)}/relations`,
      )
      setRelations(data.relations)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cargar las relaciones')
    }
  }, [workId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    let cancelled = false
    async function loadOptions() {
      try {
        const wanted = ['persons', 'roles', ...PANELS.filter((p) => p.key !== 'person_roles').map((p) => p.key)]
        const results = await Promise.all(
          wanted.map(async (key) => {
            const data = await getJson<{ options: Option[] }>(
              `${API}/options/${encodeURIComponent(key)}`,
            )
            return [key, data.options] as const
          }),
        )
        if (!cancelled) setOptions(Object.fromEntries(results))
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Error al cargar opciones')
      }
    }
    void loadOptions()
    return () => {
      cancelled = true
    }
  }, [])

  function entityOptions(panel: string): Option[] {
    return panel === 'person_roles' ? options['persons'] ?? [] : options[panel] ?? []
  }

  /** Opciones del select incluyendo siempre el valor actual (aunque no venga en la lista). */
  function withCurrent(list: Option[], value: string | number | null | undefined, label?: string | null): Option[] {
    if (value === null || value === undefined || value === '') return list
    const key = String(value)
    if (list.some((o) => String(o.value) === key)) return list
    return [{ value: key, label: label ?? key }, ...list]
  }

  async function add(panel: string, value: string, role?: string) {
    if (!value) return
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { id: value }
      if (panel === 'person_roles') body.role_id = role || ''
      await sendJson(`${API}/${encodeURIComponent(workId)}/relations/${panel}`, 'POST', body)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo añadir')
    } finally {
      setBusy(false)
    }
  }

  async function remove(panel: string, item: RelItem) {
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { id: item.ref_id }
      if (panel === 'person_roles') body.role_id = item.role_id
      await sendJson(`${API}/${encodeURIComponent(workId)}/relations/${panel}`, 'DELETE', body)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo quitar')
    } finally {
      setBusy(false)
    }
  }

  /** Modificar = borrar la relación actual y crear la nueva. */
  async function modify(panel: string, item: RelItem, nextValue: string, nextRole?: string) {
    if (nextRole !== undefined && nextRole === '') return
    setBusy(true)
    setError(null)
    try {
      const delBody: Record<string, unknown> = { id: item.ref_id }
      if (panel === 'person_roles') delBody.role_id = item.role_id
      await sendJson(`${API}/${encodeURIComponent(workId)}/relations/${panel}`, 'DELETE', delBody)
      const addBody: Record<string, unknown> = { id: nextValue }
      if (panel === 'person_roles') addBody.role_id = nextRole ?? item.role_id ?? ''
      await sendJson(`${API}/${encodeURIComponent(workId)}/relations/${panel}`, 'POST', addBody)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo modificar')
      await load()
    } finally {
      setBusy(false)
    }
  }

  function setDraftField(panel: string, field: 'value' | 'role', value: string) {
    setDraft((prev) => {
      const cur = prev[panel] ?? { value: '', role: '' }
      const next = { ...cur, [field]: value }
      // Al elegir el valor principal, si no requiere rol o ya hay rol, se añade directamente.
      if (field === 'value' && value && (panel !== 'person_roles' || next.role)) {
        void add(panel, value, next.role)
        return { ...prev, [panel]: { value: '', role: '' } }
      }
      return { ...prev, [panel]: next }
    })
  }

  return (
    <section className="relations">
      <h2 className="relations__title">Relaciones de la obra</h2>
      {error && <p className="alert alert--error">{error}</p>}

      {PANELS.map((panel) => {
        const items = relations[panel.key] ?? []
        const personRole = panel.key === 'person_roles'
        const ents = entityOptions(panel.key)
        const roles = options['roles'] ?? []
        const d = draft[panel.key] ?? { value: '', role: '' }
        return (
          <div className="rel" key={panel.key}>
            <h3 className="rel__title">
              {panel.title}
              <span className="rel__count">{items.length}</span>
              {panel.hint && <em className="rel__hint">{panel.hint}</em>}
            </h3>

            {/* Una fila por relación existente: selects (valor + rol) y X para borrar. */}
            {items.map((item) => (
              <div className="rel__add" key={`${panel.key}-${item.ref_id}-${item.role_id ?? ''}`}>
                <select
                  value={String(item.ref_id ?? '')}
                  disabled={!editing || busy}
                  onChange={(e) => void modify(panel.key, item, e.target.value, item.role_id != null ? String(item.role_id) : undefined)}
                >
                  {withCurrent(ents, item.ref_id, item.label).map((o) => (
                    <option key={String(o.value)} value={String(o.value)}>
                      {o.label ?? o.value}
                    </option>
                  ))}
                </select>
                {personRole && (
                  <select
                    value={String(item.role_id ?? '')}
                    disabled={!editing || busy}
                    onChange={(e) => void modify(panel.key, item, String(item.ref_id ?? ''), e.target.value)}
                  >
                    <option value="">— rol —</option>
                    {roles.map((o) => (
                      <option key={String(o.value)} value={String(o.value)}>
                        {o.label ?? o.value}
                      </option>
                    ))}
                  </select>
                )}
                {editing && (
                  <button
                    type="button"
                    className="btn btn--danger btn--tiny"
                    disabled={busy}
                    onClick={() => void remove(panel.key, item)}
                    title="Quitar"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}

            {/* Fila en blanco para añadir. */}
            {editing && (
              <div className="rel__add rel__add--new">
                <select
                  value={d.value}
                  disabled={busy}
                  onChange={(e) => setDraftField(panel.key, 'value', e.target.value)}
                >
                  <option value="">{personRole ? '— elegir persona —' : '— elegir —'}</option>
                  {ents.map((o) => (
                    <option key={String(o.value)} value={String(o.value)}>
                      {o.label ?? o.value}
                    </option>
                  ))}
                </select>
                {personRole && (
                  <select
                    value={d.role}
                    disabled={busy}
                    onChange={(e) => setDraftField(panel.key, 'role', e.target.value)}
                  >
                    <option value="">— rol —</option>
                    {roles.map((o) => (
                      <option key={String(o.value)} value={String(o.value)}>
                        {o.label ?? o.value}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  type="button"
                  className="btn btn--primary btn--tiny"
                  disabled={busy || !d.value || (personRole && !d.role)}
                  onClick={() => {
                    void add(panel.key, d.value, d.role)
                    setDraft((prev) => ({ ...prev, [panel.key]: { value: '', role: '' } }))
                  }}
                  title="Añadir"
                >
                  +
                </button>
              </div>
            )}
          </div>
        )
      })}
    </section>
  )
}
