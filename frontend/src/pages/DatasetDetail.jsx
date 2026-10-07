import { useEffect, useState } from 'react'
import { NavLink, Outlet, useParams, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import WorkflowBar from '../components/WorkflowBar'

const TABS = [
  { to: '',           label: 'Overview' },
  { to: 'quality',    label: 'Quality' },
  { to: 'ai',         label: 'AI Engineer' },
  { to: 'pipeline',   label: 'Pipeline' },
  { to: 'validation', label: 'Validation' },
  { to: 'analytics',  label: 'Analytics' },
  { to: 'report',     label: 'Report' },
  { to: 'benchmark',  label: 'Benchmark' },
]

function workflowStep(ds) {
  // Backend computes progress (0-6) from persisted artefacts so steps
  // 3-6 (AI Recs, Pipeline, Validate, Analytics) advance correctly.
  if (typeof ds.workflow_progress === 'number') return ds.workflow_progress
  // Fallback for older API responses
  const map = { uploaded: 0, profiling: 1, profiled: 2 }
  return map[ds.status] ?? 0
}

export default function DatasetDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [ds, setDs] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getDataset(id)
      .then(setDs)
      .catch(e => setError(e.message))
  }, [id])

  if (error) return <div className="alert alert-error">{error}</div>
  if (!ds)   return <div className="loading-row"><div className="spinner" /> Loading…</div>

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div style={{ fontSize: '.75rem', color: 'var(--text-muted)', marginBottom: '.25rem' }}>
            <span
              style={{ cursor: 'pointer', textDecoration: 'underline' }}
              onClick={() => navigate('/datasets')}
            >Datasets</span>
            {' / '}
            <span style={{ color: 'var(--text)' }}>{ds.name}</span>
          </div>
          <h1>{ds.name}</h1>
          <div className="sub" style={{ display: 'flex', gap: '1rem', marginTop: '.3rem', flexWrap: 'wrap' }}>
            <span>{ds.original_filename}</span>
            <span className="badge badge-blue">{ds.file_type.toUpperCase()}</span>
            {ds.row_count && <span>{ds.row_count.toLocaleString()} rows</span>}
            {ds.column_count && <span>{ds.column_count} columns</span>}
            <span style={{ color: 'var(--text-faint)' }}>{fmtDate(ds.created_at)}</span>
          </div>
        </div>
      </div>

      {/* Workflow bar */}
      <WorkflowBar current={workflowStep(ds)} />

      {/* Tab nav */}
      <div className="tabs">
        {TABS.map(t => (
          <NavLink
            key={t.to}
            to={t.to === '' ? `/datasets/${id}` : `/datasets/${id}/${t.to}`}
            end={t.to === ''}
            className={({ isActive }) => `tab ${isActive ? 'active' : ''}`}
          >
            {t.label}
          </NavLink>
        ))}
      </div>

      {/* Active page */}
      <Outlet context={{ ds, setDs }} />
    </div>
  )
}

function fmtDate(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
