import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

export default function Datasets() {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = () => {
    setLoading(true)
    api.listDatasets()
      .then(d => setDatasets(d.items))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleDelete = async (id, name) => {
    if (!confirm(`Delete dataset "${name}"?`)) return
    try {
      await api.deleteDataset(id)
      setDatasets(ds => ds.filter(d => d.id !== id))
    } catch (e) {
      alert(e.message)
    }
  }

  if (loading) return <div className="loading-row"><div className="spinner" /> Loading datasets…</div>
  if (error)   return <div className="alert alert-error">{error}</div>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Datasets</h1>
          <div className="sub">{datasets.length} dataset{datasets.length !== 1 ? 's' : ''} total</div>
        </div>
        <Link to="/upload" className="btn btn-primary">↑ Upload New</Link>
      </div>

      {datasets.length === 0 ? (
        <div className="empty-state">
          <div className="es-icon">⊞</div>
          <div className="es-title">No datasets yet</div>
          <div className="es-sub">Upload a CSV or XLSX to begin</div>
          <Link to="/upload" className="btn btn-primary mt-sm">Upload Dataset</Link>
        </div>
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>File</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Rows</th>
                  <th>Cols</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {datasets.map(ds => (
                  <tr key={ds.id}>
                    <td style={{ fontWeight: 600, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <Link to={`/datasets/${ds.id}`}>{ds.name}</Link>
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '.75rem', fontFamily: 'var(--font-mono)' }}>{ds.original_filename}</td>
                    <td><span className="badge badge-blue">{ds.file_type.toUpperCase()}</span></td>
                    <td style={{ color: 'var(--text-muted)' }}>{fmtBytes(ds.file_size_bytes)}</td>
                    <td>{ds.row_count?.toLocaleString() ?? '–'}</td>
                    <td>{ds.column_count ?? '–'}</td>
                    <td><StatusBadge status={ds.status} /></td>
                    <td style={{ color: 'var(--text-muted)' }}>{fmtDate(ds.created_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '.4rem' }}>
                        <Link to={`/datasets/${ds.id}`} className="btn btn-ghost btn-sm">Open</Link>
                        <button className="btn btn-danger btn-sm" onClick={() => handleDelete(ds.id, ds.name)}>✕</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const map = { uploaded: ['badge-blue', 'Uploaded'], profiling: ['badge-yellow', 'Profiling'], profiled: ['badge-green', 'Profiled'], error: ['badge-red', 'Error'] }
  const [cls, label] = map[status] || ['badge-gray', status]
  return <span className={`badge ${cls}`}>{label}</span>
}

function fmtBytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}

function fmtDate(ts) {
  if (!ts) return '–'
  return new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
