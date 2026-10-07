import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'

export default function ValidationPage() {
  const { ds } = useOutletContext()
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getValidation(ds.id)
      .then(setResults)
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [ds.id])

  if (loading) return <div className="loading-row"><div className="spinner" />Loading validation results…</div>

  if (!results.length) return (
    <div>
      <h2 style={{ marginBottom: '1rem' }}>Validation</h2>
      <div className="empty-state">
        <div className="es-icon">⊟</div>
        <div className="es-title">No validation results yet</div>
        <div className="es-sub">Execute a pipeline to generate validation results</div>
      </div>
    </div>
  )

  return (
    <div>
      <h2 style={{ marginBottom: '1rem' }}>Validation Results</h2>

      {results.map((vr, idx) => (
        <div key={vr.id} className="card mb-md">
          <div className="card-header">
            <div style={{ display: 'flex', gap: '.75rem', alignItems: 'center' }}>
              <span className="card-title">Run {results.length - idx}</span>
              <OverallBadge status={vr.overall_status} />
            </div>
            <span style={{ fontSize: '.72rem', color: 'var(--text-muted)' }}>
              {new Date(vr.created_at).toLocaleString()}
            </span>
          </div>

          {/* Before / After comparison */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            <CompareBox label="Before" data={vr.before_json} color="var(--text-muted)" />
            <CompareBox label="After"  data={vr.after_json}  color="var(--blue-light)" />
          </div>

          {/* Checks */}
          <div style={{ fontSize: '.8rem', fontWeight: 600, marginBottom: '.5rem' }}>Validation Checks</div>
          <div className="check-list">
            {vr.checks_json.map((check, i) => (
              <div key={i} className={`check-item ${check.status}`}>
                <span className="check-icon">{checkIcon(check.status)}</span>
                <div>
                  <div className="check-name">{check.name}</div>
                  <div className="check-detail">{check.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function CompareBox({ label, data, color }) {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '.85rem 1rem',
    }}>
      <div style={{ fontSize: '.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-muted)', marginBottom: '.6rem' }}>
        {label}
      </div>
      {[
        ['Rows',         data.rows?.toLocaleString()],
        ['Columns',      data.columns],
        ['Missing',      data.missing_total?.toLocaleString()],
        ['Duplicates',   data.duplicate_rows?.toLocaleString()],
      ].map(([k, v]) => (
        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.8rem', marginBottom: '.25rem' }}>
          <span style={{ color: 'var(--text-muted)' }}>{k}</span>
          <span style={{ fontWeight: 600, color }}>{v ?? '–'}</span>
        </div>
      ))}
    </div>
  )
}

function OverallBadge({ status }) {
  const map = { PASS: 'badge-green', WARNING: 'badge-yellow', FAILED: 'badge-red' }
  return <span className={`badge ${map[status] || 'badge-gray'}`}>{status}</span>
}

function checkIcon(status) {
  return status === 'PASS' ? '✓' : status === 'WARNING' ? '⚠' : '✕'
}
