import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import {
  createRow,
  getErrorMessage,
  getRow,
  getSchema,
  updateRow,
  type Row,
  type SchemaColumn,
  type TableSchema,
} from '../api'
import { metaOf } from '../tables'

interface Props {
  mode?: 'new'
}

function blankValue(column: SchemaColumn): string {
  if (column.default !== null && column.default !== undefined) return String(column.default)
  return ''
}

export default function RowForm({ mode }: Props) {
  const { table = '', pk = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const meta = metaOf(table)

  const isNew = mode === 'new'
  const [schema, setSchema] = useState<TableSchema | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [original, setOriginal] = useState<Row>({})
  const [editing, setEditing] = useState(isNew)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getSchema(table)
      .then(async (s) => {
        if (cancelled) return
        setSchema(s)
        if (isNew) {
          const next: Record<string, string> = {}
          for (const c of s.columns) {
            if (c.key === 'PRI' || c.extra.includes('auto_increment')) continue
            next[c.name] = blankValue(c)
          }
          setValues(next)
        } else {
          const response = await getRow(table, pk)
          if (cancelled) return
          setOriginal(response.row)
          const next: Record<string, string> = {}
          for (const c of s.columns) {
            const v = response.row[c.name]
            next[c.name] = v === null || v === undefined ? '' : String(v)
          }
          setValues(next)
        }
        setEditing(mode === 'new' || searchParams.get('mode') === 'edit')
      })
      .catch((e) => !cancelled && setError(getErrorMessage(e)))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table, pk, isNew])

  const pkColumn = schema?.pk ?? 'id'
  const relationOf = useMemo(() => {
    const map = new Map<string, { table: string; column: string }>()
    for (const r of schema?.relations ?? []) {
      map.set(r.column, { table: r.ref_table, column: r.ref_column })
    }
    return map
  }, [schema])

  const columns = useMemo(() => {
    const cols = schema?.columns ?? []
    if (!isNew) return cols
    // En alta no se muestran columnas autoincrementales.
    return cols.filter((c) => !c.extra.includes('auto_increment'))
  }, [schema, isNew])

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const payload: Row = {}
      for (const c of columns) {
        const raw = values[c.name] ?? ''
        if (isNew && c.extra.includes('auto_increment')) continue
        if (raw === '' && c.nullable) {
          payload[c.name] = null
        } else {
          payload[c.name] = raw
        }
      }
      if (isNew) {
        const created = await createRow(table, payload)
        const newPk = String(created.row[pkColumn] ?? '')
        navigate(`/t/${encodeURIComponent(table)}/${encodeURIComponent(newPk)}`)
      } else {
        await updateRow(table, pk, payload)
        setSearchParams({}, { replace: true })
        setEditing(false)
      }
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  function cancel() {
    if (isNew) {
      navigate(`/t/${encodeURIComponent(table)}`)
      return
    }
    if (editing) {
      const next: Record<string, string> = {}
      for (const [k, v] of Object.entries(original)) {
        next[k] = v === null || v === undefined ? '' : String(v)
      }
      setValues(next)
      setSearchParams({}, { replace: true })
      setEditing(false)
    } else {
      navigate(`/t/${encodeURIComponent(table)}`)
    }
  }

  const title = isNew ? `Nueva fila en ${meta.label}` : `${meta.label} · ${pk}`

  return (
    <section>
      <nav className="breadcrumb" aria-label="Ruta">
        <Link to="/">Mantenimiento</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/t/${encodeURIComponent(table)}`}>{meta.label}</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{isNew ? 'nueva' : pk}</span>
      </nav>

      <div className="page-head">
        <div>
          <h1>{title}</h1>
          <p className="lede">
            <code>{table}</code> · {editing ? 'edición' : 'solo lectura'}
          </p>
        </div>
        <div className="page-head__actions">
          {!editing && !isNew && (
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setSearchParams({ mode: 'edit' })}
            >
              Editar
            </button>
          )}
          {editing && (
            <>
              <button type="button" className="btn btn--ghost" onClick={cancel} disabled={saving}>
                Cancelar
              </button>
              <button type="button" className="btn btn--primary" onClick={save} disabled={saving}>
                {saving ? 'Guardando…' : 'Guardar'}
              </button>
            </>
          )}
          {!editing && (
            <button type="button" className="btn btn--ghost" onClick={cancel}>
              Volver
            </button>
          )}
        </div>
      </div>

      {error && <p className="alert alert--error">{error}</p>}
      {loading && <p className="empty">Cargando…</p>}

      {!loading && schema && (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault()
            if (editing) void save()
          }}
        >
          {columns.map((column) => {
            const rel = relationOf.get(column.name)
            const value = values[column.name] ?? ''
            const isPk = column.name === pkColumn
            const readOnly = !editing || (isPk && !isNew)
            return (
              <div className="form__row" key={column.name}>
                <label className="form__label" htmlFor={`f-${column.name}`}>
                  <code>{column.name}</code>
                  <small>{column.type}</small>
                </label>
                <div className="form__control">
                  <input
                    id={`f-${column.name}`}
                    className="input"
                    value={value}
                    readOnly={readOnly}
                    placeholder={column.nullable ? 'NULL' : ''}
                    onChange={(e) =>
                      setValues((prev) => ({ ...prev, [column.name]: e.target.value }))
                    }
                  />
                  {rel && value !== '' && (
                    <Link
                      className="btn btn--ghost btn--tiny"
                      to={`/t/${encodeURIComponent(rel.table)}/${encodeURIComponent(value)}`}
                      title={`Abrir ${rel.table}.${rel.column}`}
                    >
                      → {rel.table}
                    </Link>
                  )}
                </div>
              </div>
            )
          })}
          {editing && (
            <div className="form__footer">
              <button type="button" className="btn btn--ghost" onClick={cancel} disabled={saving}>
                Cancelar
              </button>
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          )}
        </form>
      )}
    </section>
  )
}
