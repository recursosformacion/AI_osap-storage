import { useCallback, useEffect, useState } from 'react'

import {
  createRepresentation,
  deleteRepresentation,
  getErrorMessage,
  getRepresentation,
  listRepresentations,
  updateRepresentation,
  type RepresentationDetail,
  type RepresentationListItem,
  type RepresentationPayload,
} from '../api'

const PAGE = 25

interface Draft {
  works_id: string
  origin: string
  origin_id: string
  cpdlno: string
  type: string
  license: string
  source_name: string
}

const EMPTY: Draft = {
  works_id: '',
  origin: 'cpdl',
  origin_id: '',
  cpdlno: '',
  type: 'edition',
  license: '',
  source_name: '',
}

function toPayload(draft: Draft): RepresentationPayload {
  const payload: RepresentationPayload = {
    works_id: Number(draft.works_id),
    origin: draft.origin.trim(),
    type: draft.type.trim(),
    license: draft.license.trim(),
  }
  if (draft.origin_id.trim()) payload.origin_id = draft.origin_id.trim()
  if (draft.cpdlno.trim()) payload.cpdlno = Number(draft.cpdlno)
  if (draft.source_name.trim()) payload.source_name = draft.source_name.trim()
  return payload
}

export default function Representations() {
  const [items, setItems] = useState<RepresentationListItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [filters, setFilters] = useState({ origin: '', license: '', works_id: '', q: '' })
  const [detail, setDetail] = useState<RepresentationDetail | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await listRepresentations({ ...filters, limit: PAGE, offset })
      setItems(result.items)
      setTotal(result.total)
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setBusy(false)
    }
  }, [filters, offset])

  useEffect(() => {
    void load()
  }, [load])

  async function open(id: number) {
    try {
      setDetail(await getRepresentation(id))
      setDraft(null)
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  function editFromDetail() {
    if (!detail) return
    setDraft({
      works_id: String(detail.works_id),
      origin: detail.origin,
      origin_id: detail.origin_id ?? '',
      cpdlno: detail.cpdlno ? String(detail.cpdlno) : '',
      type: detail.type,
      license: detail.license,
      source_name: detail.source_name ?? '',
    })
  }

  async function save() {
    if (!draft) return
    setBusy(true)
    setError(null)
    try {
      const payload = toPayload(draft)
      const saved = detail
        ? await updateRepresentation(detail.id, payload)
        : await createRepresentation(payload)
      setDetail(saved)
      setDraft(null)
      await load()
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!detail) return
    setBusy(true)
    try {
      await deleteRepresentation(detail.id)
      setDetail(null)
      await load()
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const pages = Math.max(1, Math.ceil(total / PAGE))

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Representaciones</h1>
          <p className="lede">
            {total} representaciones · cada una con sus recursos (de <code>works_resources</code>) y
            editores (de <code>representation_persons</code>).
          </p>
        </div>
        <button type="button" className="btn" onClick={() => setDraft({ ...EMPTY })}>
          Nueva representación
        </button>
      </div>

      {error && <p className="alert alert--error">{error}</p>}

      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault()
          setOffset(0)
          void load()
        }}
      >
        <label className="field field--inline">
          <span>Origen</span>
          <input
            value={filters.origin}
            placeholder="cpdl"
            onChange={(e) => setFilters({ ...filters, origin: e.target.value })}
          />
        </label>
        <label className="field field--inline">
          <span>Licencia</span>
          <input
            value={filters.license}
            onChange={(e) => setFilters({ ...filters, license: e.target.value })}
          />
        </label>
        <label className="field field--inline">
          <span>Obra (works_id)</span>
          <input
            value={filters.works_id}
            onChange={(e) => setFilters({ ...filters, works_id: e.target.value })}
          />
        </label>
        <label className="field field--inline">
          <span>Origin id / nombre</span>
          <input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
        </label>
        <button type="submit" className="btn" disabled={busy}>
          Buscar
        </button>
      </form>

      <table className="table">
        <thead>
          <tr>
            <th>id</th>
            <th>obra</th>
            <th>origen</th>
            <th>origin_id</th>
            <th>tipo</th>
            <th>licencia</th>
            <th>recursos</th>
            <th>editores</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} onClick={() => void open(item.id)} className="row--link">
              <td>{item.id}</td>
              <td>{item.works_id}</td>
              <td>{item.origin}</td>
              <td>{item.origin_id}</td>
              <td>{item.type}</td>
              <td>{item.license}</td>
              <td>{item.resources}</td>
              <td>{item.editors}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="pager">
        <button type="button" className="btn" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>
          ←
        </button>
        <span>
          {Math.floor(offset / PAGE) + 1} / {pages}
        </span>
        <button
          type="button"
          className="btn"
          disabled={offset + PAGE >= total}
          onClick={() => setOffset(offset + PAGE)}
        >
          →
        </button>
      </div>

      {detail && (
        <section className="group">
          <h2 className="group__title">
            Representación {detail.id}
            <button type="button" className="btn" onClick={editFromDetail}>
              Editar
            </button>
            <button type="button" className="btn" onClick={() => void remove()} disabled={busy}>
              Borrar
            </button>
          </h2>
          <dl className="kv">
            <dt>Obra</dt>
            <dd>
              {detail.work?.id} — {detail.work?.title} ({detail.work?.origin})
            </dd>
            <dt>Origen</dt>
            <dd>
              {detail.origin} · {detail.origin_id} {detail.cpdlno ? `· CPDLno ${detail.cpdlno}` : ''}
            </dd>
            <dt>Tipo / licencia</dt>
            <dd>
              {detail.type} · {detail.license}
            </dd>
          </dl>

          <h3>Recursos ({detail.resources.length}) — de works_resources</h3>
          <table className="table">
            <thead>
              <tr>
                <th>id</th>
                <th>tipo</th>
                <th>nombre</th>
                <th>estado</th>
                <th>file_id</th>
                <th>url</th>
              </tr>
            </thead>
            <tbody>
              {detail.resources.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.type}</td>
                  <td>{r.name}</td>
                  <td>{r.status}</td>
                  <td>{r.file_id ?? '—'}</td>
                  <td>
                    {r.url ? (
                      <a href={r.url} target="_blank" rel="noreferrer">
                        enlace
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Editores ({detail.editors.length}) — de representation_persons</h3>
          <table className="table">
            <thead>
              <tr>
                <th>id</th>
                <th>persona</th>
                <th>rol</th>
                <th>nombre</th>
              </tr>
            </thead>
            <tbody>
              {detail.editors.map((e) => (
                <tr key={e.id}>
                  <td>{e.id}</td>
                  <td>{e.person_name ?? e.person_id ?? '—'}</td>
                  <td>{e.role_id}</td>
                  <td>{e.name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {draft && (
        <section className="group">
          <h2 className="group__title">{detail ? `Editar ${detail.id}` : 'Nueva representación'}</h2>
          <div className="filters">
            {(
              [
                ['works_id', 'Obra (works_id) *'],
                ['origin', 'Origen *'],
                ['origin_id', 'origin_id'],
                ['cpdlno', 'CPDLno'],
                ['type', 'Tipo'],
                ['license', 'Licencia'],
                ['source_name', 'source_name'],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="field field--inline">
                <span>{label}</span>
                <input
                  value={draft[key]}
                  onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                />
              </label>
            ))}
          </div>
          <div className="pager">
            <button
              type="button"
              className="btn"
              onClick={() => void save()}
              disabled={busy || !draft.works_id || !draft.origin}
            >
              Guardar
            </button>
            <button type="button" className="btn" onClick={() => setDraft(null)}>
              Cancelar
            </button>
          </div>
        </section>
      )}
    </section>
  )
}
