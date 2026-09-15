import { Link, Navigate, Route, Routes } from 'react-router-dom'

import Menu from './pages/Menu'
import RowForm from './pages/RowForm'
import TableList from './pages/TableList'

export default function App() {
  return (
    <div className="app">
      <header className="masthead">
        <Link className="masthead__brand" to="/">
          <span className="monogram" aria-hidden="true">
            OS
          </span>
          <span>
            <strong>osap-storage</strong>
            <em>mantenimiento</em>
          </span>
        </Link>
      </header>

      <main className="main">
        <Routes>
          <Route path="/" element={<Menu />} />
          <Route path="/t/:table" element={<TableList />} />
          <Route path="/t/:table/new" element={<RowForm mode="new" />} />
          <Route path="/t/:table/:pk" element={<RowForm />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
