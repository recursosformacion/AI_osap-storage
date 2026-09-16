import { useCallback, useEffect, useState } from 'react'

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
  const [selection, setSelection] = useState<Record<string, string>>({})
  const [roleSelection, setRoleSelection] = useState<Record<string, string>>({})
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

  async function add(panel: string) {
    const value = selection[panel]
    if (!value) return
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { id: value }
      if (panel === 'person_roles') body.role_id = roleSelection[panel] || ''
      await sendJson(`${API}/${encodeURIComponent(workId)}/relations/${panel}`, 'POST', body)
      setSelection((prev) => ({ ...prev, [panel]: '' }))
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

  function itemText(panel: string, item: RelItem): string {
    const parts = [item.label ?? String(item.ref_id ?? '')]
    if (panel === 'person_roles' && item.role_name) parts.push(`— ${item.role_name}`)
    if (panel === 'instruments' && item.quantity && item.quantity > 1) parts.push(`×${item.quantity}`)
    if (panel === 'voices' && item.context) parts.push(`(${item.context})`)
    return parts.join(' ')
  }

  return (
    <section className="relations">
      <h2 className="relations__title">Relaciones de la obra</h2>
      {error && <p className="alert alert--error">{error}</p>}

      {PANELS.map((panel) => {
        const items = relations[panel.key] ?? []
        const personRole = panel.key === 'person_roles'
        return (
          <div className="rel" key={panel.key}>
            <h3 className="rel__title">
              {panel.title}
              <span className="rel__count">{items.length}</span>
              {panel.hint && <em className="rel__hint">{panel.hint}</em>}
            </h3>

            <ul className="rel__items">
              {items.length === 0 && <li className="rel__empty">Sin relaciones.</li>}
              {items.map((item) => (
                <li key={`${panel.key}-${item.ref_id}-${item.role_id ?? ''}`} className="rel__item">
                  <span>{itemText(panel.key, item)}</span>
                  {editing && (
                    <button
                      type="button"
                      className="btn btn--danger btn--tiny"
                      disabled={busy}
                      onClick={() => remove(panel.key, item)}
                      title="Quitar"
                    >
                      ×
                    </button>
                  )}
                </li>
              ))}
            </ul>

            {editing && (
              <div className="rel__add">
                <select
                  value={selection[panel.key] ?? ''}
                  onChange={(e) =>
                    setSelection((prev) => ({ ...prev, [panel.key]: e.target.value }))
                  }
                >
                  <option value="">
                    {personRole ? '— elegir persona —' : '— elegir —'}
                  </option>
                  {(options[personRole ? 'persons' : panel.key] ?? []).map((o) => (
                    <option key={String(o.value)} value={String(o.value)}>
                      {o.label ?? o.value}
                    </option>
                  ))}
                </select>
                {personRole && (
                  <select
                    value={roleSelection[panel.key] ?? ''}
                    onChange={(e) =>
                      setRoleSelection((prev) => ({ ...prev, [panel.key]: e.target.value }))
                    }
                  >
                    <option value="">— rol —</option>
                    {(options['roles'] ?? []).map((o) => (
                      <option key={String(o.value)} value={String(o.value)}>
                        {o.label ?? o.value}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  type="button"
                  className="btn btn--primary btn--tiny"
                  disabled={busy || !selection[panel.key] || (personRole && !roleSelection[panel.key])}
                  onClick={() => add(panel.key)}
                >
                  Añadir
                </button>
              </div>
            )}
          </div>
        )
      })}
    </section>
  )
}
