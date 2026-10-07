import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import QualityScore from '../components/QualityScore'

const ISSUE_TYPE_LABELS = {
  missing_values:           { label: 'Missing Values',          icon: '○', color: 'var(--blue-light)' },
  duplicates:               { label: 'Duplicates',              icon: '⧉', color: 'var(--yellow-light)' },
  outliers:                 { label: 'Outliers',                icon: '⚡', color: 'var(--red-light)' },
  inconsistent_categories:  { label: 'Inconsistent Categories', icon: '≠', color: 'var(--purple-light)' },
  invalid_dates:            { label: 'Invalid Dates',           icon: '📅', color: 'var(--yellow-light)' },
  type_anomalies:           { label: 'Type Anomalies',          icon: '?', color: 'var(--text-muted)' },
}

export default function QualityPage() {
  const { ds } = useOutletContext()
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error,   setError]   = useState(null)

  const load = () => {
    setLoading(true)
    api.getQuality(ds.id)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoading(false))
  }

  useEffect(load, [ds.id])

  const runQuality = async () => {
    setRunning(true); setError(null)
    try {
      const r = await api.runQuality(ds.id)
      setReport(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  if (loading) return <div className="loading-row"><div className="spinner" />Loading quality report…</div>

  // Group issues by type
  const issuesByType = {}
  for (const issue of report?.issues_json ?? []) {
    if (!issuesByType[issue.type]) issuesByType[issue.type] = []
    issuesByType[issue.type].push(issue)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2>Data Quality Analysis</h2>
        <button className="btn btn-blue" onClick={runQuality} disabled={running}>
          {running ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Analysing…</> : '↺ Re-analyse'}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {!report ? (
        <div className="empty-state">
          <div className="es-icon">⊟</div>
          <div className="es-title">No quality report yet</div>
          <div className="es-sub">Run profiling first, then click Re-analyse</div>
        </div>
      ) : (
        <>
          {/* Score */}
          <div className="card mb-md">
            <div className="card-header">
              <span className="card-title">Overall Quality Score</span>
              <span style={{ fontSize: '.75rem', color: 'var(--text-muted)' }}>
                {new Date(report.created_at).toLocaleString()}
              </span>
            </div>
            <QualityScore score={report.quality_score} breakdown={report.score_breakdown_json} />
          </div>

          {/* Issue cards */}
          <h3 style={{ marginBottom: '.75rem' }}>Issues by Category</h3>
          <div className="issue-grid">
            {Object.entries(ISSUE_TYPE_LABELS).map(([type, meta]) => {
              const items = issuesByType[type] || []
              return (
                <div key={type} className="issue-card">
                  <div className="ic-type">{meta.icon} {meta.label}</div>
                  <div className="ic-count" style={{ color: items.length > 0 ? meta.color : 'var(--accent)' }}>
                    {items.length}
                  </div>
                  <div className="ic-desc">
                    {items.length === 0
                      ? 'No issues detected'
                      : `${items.length} column${items.length > 1 ? 's' : ''} affected`}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Issue detail table */}
          {report.issues_json?.length > 0 && (
            <div className="card mt-md">
              <div className="card-header"><span className="card-title">Issue Details</span></div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Type</th><th>Column</th><th>Severity</th><th>Value</th><th>Description</th></tr>
                  </thead>
                  <tbody>
                    {report.issues_json.map((issue, i) => (
                      <tr key={i}>
                        <td><span className="badge badge-gray" style={{ fontSize: '.68rem' }}>{issue.type}</span></td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '.8rem' }}>{issue.column ?? '–'}</td>
                        <td><SeverityBadge sev={issue.severity} /></td>
                        <td style={{ color: 'var(--text-muted)' }}>{issue.value != null ? `${issue.value}%` : '–'}</td>
                        <td style={{ fontSize: '.78rem', color: 'var(--text-muted)' }}>{issue.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Score methodology note */}
          <div className="alert alert-info mt-md" style={{ fontSize: '.775rem' }}>
            <strong>Scoring methodology:</strong> Missing values (30 pts) + Duplicates (20 pts) + Outliers (15 pts) +
            Inconsistent categories (15 pts) + Invalid dates (10 pts) + Type anomalies (10 pts).
            All values are computed deterministically by Python — not estimated by the AI.
          </div>
        </>
      )}
    </div>
  )
}

function SeverityBadge({ sev }) {
  const map = { low: 'badge-blue', medium: 'badge-yellow', high: 'badge-red', critical: 'badge-red', none: 'badge-green' }
  return <span className={`badge ${map[sev] || 'badge-gray'}`}>{sev}</span>
}
