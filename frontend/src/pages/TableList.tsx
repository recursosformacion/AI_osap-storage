import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  deleteRow,
  getErrorMessage,
  getRows,
  getSchema,
  type Row,
  type TableSchema,
} from '../api'
import { displayColumns, metaOf } from '../tables'

const PAGE_SIZES = [25, 50, 100]

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'sí' : 'no'
  const text = String(value)
  return text === '' ? '—' : text
}

export default function TableList() {
  const { table = '' } = useParams()
  const meta = metaOf(table)

  const [schema, setSchema] = useState<TableSchema | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<{ pk: string; row: Row } | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const pk = schema?.pk ?? 'id'
  const columns = useMemo(
    () => (schema ? displayColumns(table, schema.columns) : []),
    [schema, table],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [schemaResponse, rowsResponse] = await Promise.all([
        getSchema(table),
        getRows(table, limit, offset, debounced || undefined),
      ])
      setSchema(schemaResponse)
      setRows(rowsResponse.rows)
      setTotal(rowsResponse.total)
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [table, limit, offset, debounced])

  useEffect(() => {
    void load()
  }, [load])

  const visibleRows = useMemo(() => rows, [rows])

  const pageEnd = Math.min(offset + rows.length, total)

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleteError(null)
    try {
      await deleteRow(table, pendingDelete.pk)
      setPendingDelete(null)
      await load()
    } catch (e) {
      setDeleteError(getErrorMessage(e))
    }
  }

  return (
    <section>
      <nav className="breadcrumb" aria-label="Ruta">
        <Link to="/">Mantenimiento</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{meta.label}</span>
      </nav>

      <div className="page-head">
        <div>
          <h1>{meta.label}</h1>
          <p className="lede">
            <code>{table}</code> · {loading ? 'cargando…' : `${total} filas`}
          </p>
        </div>
        <div className="page-head__actions">
          <label className="field field--inline">
            <span>Buscar (toda la tabla)</span>
            <input
              type="search"
              value={query}
              placeholder="texto…"
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <Link className="btn btn--primary" to={`/t/${encodeURIComponent(table)}/new`}>
            Nueva fila
          </Link>
        </div>
      </div>

      {error && <p className="alert alert--error">{error}</p>}

      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
              <th scope="col" className="grid__actions-col">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={columns.length + 1} className="grid__state">
                  Cargando…
                </td>
              </tr>
            )}
            {!loading && visibleRows.length === 0 && (
              <tr>
                <td colSpan={columns.length + 1} className="grid__state">
                  {query ? `Ninguna fila coincide con «${query}».` : 'No hay filas.'}
                </td>
              </tr>
            )}
            {visibleRows.map((row) => {
              const pkValue = String(row[pk] ?? '')
              return (
                <tr key={pkValue}>
                  {columns.map((column) => (
                    <td key={column} title={formatCell(row[column])}>
                      {formatCell(row[column])}
                    </td>
                  ))}
                  <td className="grid__actions">
                    <Link className="btn btn--ghost" to={`/t/${encodeURIComponent(table)}/${encodeURIComponent(pkValue)}`}>
                      Ver
                    </Link>
                    <Link
                      className="btn btn--ghost"
                      to={`/t/${encodeURIComponent(table)}/${encodeURIComponent(pkValue)}?mode=edit`}
                    >
                      Editar
                    </Link>
                    <button
                      type="button"
                      className="btn btn--danger"
                      onClick={() => {
                        setDeleteError(null)
                        setPendingDelete({ pk: pkValue, row })
                      }}
                    >
                      Borrar
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <label className="field field--inline">
          <span>Filas por página</span>
          <select
            value={limit}
            onChange={(e) => {
              setLimit(Number(e.target.value))
              setOffset(0)
            }}
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <span className="pager__range">
          {total === 0 ? '0' : `${offset + 1}–${pageEnd}`} de {total}
        </span>
        <button
          type="button"
          className="btn btn--ghost"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - limit))}
        >
          Anterior
        </button>
        <button
          type="button"
          className="btn btn--ghost"
          disabled={pageEnd >= total}
          onClick={() => setOffset(offset + limit)}
        >
          Siguiente
        </button>
      </div>

      {pendingDelete && (
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="del-title">
          <div className="modal__box">
            <h2 id="del-title">Borrar fila</h2>
            <p>
              Vas a borrar <code>{pk}</code> = <strong>{pendingDelete.pk}</strong> de{' '}
              <code>{table}</code>.
            </p>
            <p className="modal__warn">
              Esta acción no se puede deshacer. Si otras tablas la referencian (claves
              foráneas), el borrado puede fallar o arrastrar dependencias en cascada.
            </p>
            {deleteError && <p className="alert alert--error">{deleteError}</p>}
            <div className="modal__actions">
              <button type="button" className="btn btn--ghost" onClick={() => setPendingDelete(null)}>
                Cancelar
              </button>
              <button type="button" className="btn btn--danger" onClick={confirmDelete}>
                Borrar definitivamente
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
