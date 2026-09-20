import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { getErrorMessage, listTables } from '../api'
import { groupTables, metaOf } from '../tables'

export default function Menu() {
  const [tables, setTables] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listTables()
      .then((r) => setTables(r.tables))
      .catch((e) => setError(getErrorMessage(e)))
      .finally(() => setLoading(false))
  }, [])

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const filtered = needle
      ? tables.filter(
          (t) =>
            t.toLowerCase().includes(needle) ||
            metaOf(t).label.toLowerCase().includes(needle),
        )
      : tables
    return groupTables(filtered)
  }, [tables, query])

  const total = tables.length

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Mantenimiento</h1>
          <p className="lede">
            {loading ? 'Cargando tablas…' : `${total} tablas expuestas al mantenimiento.`}
          </p>
        </div>
        <label className="field field--inline">
          <span>Buscar tabla</span>
          <input
            type="search"
            value={query}
            placeholder="works, persons, instruments…"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>

      <p>
        <Link className="btn" to="/representations">
          Representaciones (obras → representación → recursos)
        </Link>
      </p>

      {error && <p className="alert alert--error">{error}</p>}

      {!loading && groups.length === 0 && (
        <p className="empty">Ninguna tabla coincide con «{query}».</p>
      )}

      {groups.map(({ group, tables: items }) => (
        <section key={group} className="group">
          <h2 className="group__title">
            {group}
            <span className="group__count">{items.length}</span>
          </h2>
          <ul className="cards">
            {items.map((table) => (
              <li key={table}>
                <Link className="card" to={`/t/${encodeURIComponent(table)}`}>
                  <span className="card__label">{metaOf(table).label}</span>
                  <code className="card__table">{table}</code>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </section>
  )
}
