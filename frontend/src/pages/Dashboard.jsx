import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([api.dashboard(), api.listDatasets()])
      .then(([s, d]) => { setStats(s); setDatasets(d.items) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading-row"><div className="spinner" /> Loading dashboard…</div>
  if (error)   return <div className="alert alert-error">{error}</div>

  const score = stats?.average_quality_score
  const scoreColor = score == null ? 'var(--text-muted)' : score >= 80 ? 'var(--accent)' : score >= 60 ? 'var(--yellow)' : 'var(--red)'

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <div className="sub">Kristik Engineering Copilot — overview</div>
        </div>
        <Link to="/upload" className="btn btn-primary">↑ Upload Dataset</Link>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="label">Total Datasets</div>
          <div className="value">{stats?.total_datasets ?? 0}</div>
          <div className="sub">uploaded files</div>
        </div>
        <div className="stat-card">
          <div className="label">Avg Quality Score</div>
          <div className="value" style={{ color: scoreColor }}>
            {score != null ? score.toFixed(1) : '–'}
          </div>
          <div className="sub">out of 100</div>
        </div>
        <div className="stat-card">
          <div className="label">Issues Detected</div>
          <div className="value" style={{ color: 'var(--yellow-light)' }}>{stats?.total_issues_detected ?? 0}</div>
          <div className="sub">across all datasets</div>
        </div>
        <div className="stat-card">
          <div className="label">Pipelines</div>
          <div className="value" style={{ color: 'var(--blue-light)' }}>{stats?.recent_pipelines ?? 0}</div>
          <div className="sub">generated</div>
        </div>
      </div>

      {/* Recent datasets */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Recent Datasets</span>
          <Link to="/datasets" className="btn btn-ghost btn-sm">View all</Link>
        </div>

        {datasets.length === 0 ? (
          <div className="empty-state">
            <div className="es-icon">⊞</div>
            <div className="es-title">No datasets yet</div>
            <div className="es-sub">Upload a CSV or XLSX file to get started</div>
            <Link to="/upload" className="btn btn-primary mt-sm">Upload Dataset</Link>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Rows</th>
                  <th>Columns</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {datasets.slice(0, 8).map(ds => (
                  <tr key={ds.id}>
                    <td style={{ fontWeight: 600 }}>{ds.name}</td>
                    <td><span className="badge badge-blue">{ds.file_type.toUpperCase()}</span></td>
                    <td>{ds.row_count?.toLocaleString() ?? '–'}</td>
                    <td>{ds.column_count ?? '–'}</td>
                    <td><StatusBadge status={ds.status} /></td>
                    <td style={{ color: 'var(--text-muted)' }}>{fmtDate(ds.created_at)}</td>
                    <td>
                      <Link to={`/datasets/${ds.id}`} className="btn btn-ghost btn-sm">Open →</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Quick-start guide */}
      {datasets.length === 0 && (
        <div className="card mt-md">
          <div className="card-header"><span className="card-title">Quick Start</span></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            {[
              { n: 1, t: 'Upload',    d: 'Upload a CSV or XLSX dataset' },
              { n: 2, t: 'Profile',   d: 'Automatic data profiling' },
              { n: 3, t: 'Quality',   d: 'Deterministic quality scoring' },
              { n: 4, t: 'AI Recs',   d: 'AI-generated recommendations' },
              { n: 5, t: 'Pipeline',  d: 'Generate & execute pipeline' },
              { n: 6, t: 'Report',    d: 'Export comprehensive report' },
            ].map(s => (
              <div key={s.n} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '.85rem' }}>
                <div style={{ fontSize: '.65rem', color: 'var(--blue-light)', fontWeight: 700, marginBottom: '.25rem' }}>STEP {s.n}</div>
                <div style={{ fontWeight: 600, marginBottom: '.2rem' }}>{s.t}</div>
                <div style={{ fontSize: '.75rem', color: 'var(--text-muted)' }}>{s.d}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const map = {
    uploaded:  ['badge-blue',   'Uploaded'],
    profiling: ['badge-yellow', 'Profiling'],
    profiled:  ['badge-green',  'Profiled'],
    error:     ['badge-red',    'Error'],
  }
  const [cls, label] = map[status] || ['badge-gray', status]
  return <span className={`badge ${cls}`}>{label}</span>
}

function fmtDate(ts) {
  if (!ts) return '–'
  return new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
