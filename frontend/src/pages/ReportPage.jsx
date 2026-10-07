import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import QualityScore from '../components/QualityScore'

export default function ReportPage() {
  const { ds } = useOutletContext()
  const [report,  setReport]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    setLoading(true)
    api.getReport(ds.id)
      .then(setReport)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [ds.id])

  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${ds.name}_report.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) return <div className="loading-row"><div className="spinner" />Generating report…</div>
  if (error)   return <div className="alert alert-error">{error}</div>

  const r = report
  const applied  = r.recommendations?.filter(x => x.status === 'applied')  || []
  const rejected = r.recommendations?.filter(x => x.status === 'rejected') || []
  const pending  = r.recommendations?.filter(x => x.status === 'pending')  || []
  const lastVal  = r.validation_results?.[0]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '.5rem' }}>
        <div>
          <h2>Final Report</h2>
          <div style={{ fontSize: '.8rem', color: 'var(--text-muted)', marginTop: '.2rem' }}>
            Comprehensive data engineering pipeline summary
          </div>
        </div>
        <div style={{ display: 'flex', gap: '.5rem' }}>
          <button className="btn btn-ghost" onClick={exportJSON}>⬇ Export JSON</button>
        </div>
      </div>

      {/* 1. Dataset Summary */}
      <Section title="1. Dataset Summary">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '.75rem' }}>
          {[
            ['Name',      r.dataset?.name],
            ['File',      r.dataset?.filename],
            ['Rows',      r.dataset?.rows?.toLocaleString()],
            ['Columns',   r.dataset?.columns],
            ['Size',      fmtBytes(r.dataset?.file_size_bytes)],
            ['Uploaded',  fmtDate(r.dataset?.created_at)],
          ].map(([k, v]) => (
            <div key={k} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '.75rem' }}>
              <div style={{ fontSize: '.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: '.25rem' }}>{k}</div>
              <div style={{ fontWeight: 600, fontSize: '.875rem' }}>{v || '–'}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* 2. Quality Score */}
      {r.quality_score != null && (
        <Section title="2. Data Quality Score">
          <QualityScore score={r.quality_score} breakdown={r.score_breakdown} />
        </Section>
      )}

      {/* 3. Detected Issues */}
      {r.issues_detected?.length > 0 && (
        <Section title="3. Detected Issues">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Type</th><th>Column</th><th>Severity</th><th>Description</th></tr></thead>
              <tbody>
                {r.issues_detected.map((issue, i) => (
                  <tr key={i}>
                    <td><span className="badge badge-gray" style={{ fontSize: '.68rem' }}>{issue.type}</span></td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '.78rem' }}>{issue.column || '–'}</td>
                    <td><SevBadge sev={issue.severity} /></td>
                    <td style={{ fontSize: '.78rem', color: 'var(--text-muted)' }}>{issue.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* 4. Transformations */}
      <Section title="4. Applied Transformations">
        {applied.length === 0
          ? <div className="text-muted" style={{ fontSize: '.8rem' }}>No transformations applied.</div>
          : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem' }}>
              {applied.map((rec, i) => (
                <div key={i} style={{ display: 'flex', gap: '.75rem', alignItems: 'flex-start', padding: '.6rem .85rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', borderLeft: '3px solid var(--accent)' }}>
                  <span className="badge badge-green" style={{ flexShrink: 0 }}>Applied</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '.8rem' }}>
                      {rec.action}{rec.column ? ` → ${rec.column}` : ''}
                    </div>
                    {rec.reason && <div style={{ fontSize: '.75rem', color: 'var(--text-muted)', marginTop: '.15rem' }}>{rec.reason}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        {rejected.length > 0 && (
          <div style={{ marginTop: '.75rem', fontSize: '.75rem', color: 'var(--text-muted)' }}>
            {rejected.length} recommendation{rejected.length > 1 ? 's' : ''} rejected.
            {pending.length > 0 && ` ${pending.length} still pending.`}
          </div>
        )}
      </Section>

      {/* 5. Validation */}
      {lastVal && (
        <Section title="5. Validation Results">
          <div style={{ display: 'flex', gap: '.75rem', alignItems: 'center', marginBottom: '.75rem' }}>
            <span style={{ fontWeight: 600 }}>Overall Status:</span>
            <OverallBadge status={lastVal.overall_status} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '.75rem' }}>
            <CompareBox label="Before" data={lastVal.before} />
            <CompareBox label="After"  data={lastVal.after} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem' }}>
            {lastVal.checks?.map((c, i) => (
              <div key={i} style={{ display: 'flex', gap: '.5rem', alignItems: 'flex-start', fontSize: '.8rem' }}>
                <span style={{ color: c.status === 'PASS' ? 'var(--accent)' : c.status === 'WARNING' ? 'var(--yellow-light)' : 'var(--red-light)' }}>
                  {c.status === 'PASS' ? '✓' : c.status === 'WARNING' ? '⚠' : '✕'}
                </span>
                <span style={{ fontWeight: 600 }}>{c.name}:</span>
                <span style={{ color: 'var(--text-muted)' }}>{c.detail}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* 6. Pipeline Summary */}
      {r.pipelines?.length > 0 && (
        <Section title="6. Pipeline Summary">
          {r.pipelines.map((p, i) => (
            <div key={i} style={{ marginBottom: '.75rem', padding: '.75rem 1rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div style={{ display: 'flex', gap: '.75rem', alignItems: 'center', marginBottom: '.4rem' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{p.name}</span>
                <PipelineBadge status={p.status} />
                {p.execution_time_s && <span style={{ fontSize: '.75rem', color: 'var(--text-muted)' }}>⏱ {p.execution_time_s}s</span>}
              </div>
              <div style={{ fontSize: '.75rem', color: 'var(--text-muted)' }}>{p.steps?.length ?? 0} transformation steps</div>
            </div>
          ))}
        </Section>
      )}

      {/* 7. Profile Summary */}
      {r.profile_summary && (
        <Section title="7. Column Summary">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: '.75rem', fontSize: '.8rem' }}>
            <ColList label="Numerical" cols={r.profile_summary.numerical_columns} color="var(--blue-light)" />
            <ColList label="Categorical" cols={r.profile_summary.categorical_columns} color="var(--purple-light)" />
            <ColList label="Date" cols={r.profile_summary.date_columns} color="var(--yellow-light)" />
          </div>
        </Section>
      )}
    </div>
  )
}

/* ---- Helpers ---- */

function Section({ title, children }) {
  return (
    <div className="card mb-md">
      <div className="card-header"><span className="card-title">{title}</span></div>
      {children}
    </div>
  )
}

function ColList({ label, cols, color }) {
  return (
    <div>
      <div style={{ fontSize: '.7rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '.4rem' }}>{label}</div>
      {!cols?.length
        ? <div style={{ color: 'var(--text-faint)' }}>None</div>
        : cols.map(c => (
          <div key={c} style={{ fontFamily: 'var(--font-mono)', color, fontSize: '.8rem', marginBottom: '.15rem' }}>{c}</div>
        ))}
    </div>
  )
}

function CompareBox({ label, data }) {
  const color = label === 'After' ? 'var(--blue-light)' : 'var(--text-muted)'
  return (
    <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '.75rem' }}>
      <div style={{ fontSize: '.68rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '.5rem' }}>{label}</div>
      {[['Rows', data?.rows?.toLocaleString()], ['Missing', data?.missing_total], ['Duplicates', data?.duplicate_rows]].map(([k, v]) => (
        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.8rem', marginBottom: '.2rem' }}>
          <span style={{ color: 'var(--text-muted)' }}>{k}</span>
          <span style={{ fontWeight: 600, color }}>{v ?? '–'}</span>
        </div>
      ))}
    </div>
  )
}

function SevBadge({ sev }) {
  const m = { low: 'badge-blue', medium: 'badge-yellow', high: 'badge-red', critical: 'badge-red' }
  return <span className={`badge ${m[sev] || 'badge-gray'}`}>{sev}</span>
}

function OverallBadge({ status }) {
  const m = { PASS: 'badge-green', WARNING: 'badge-yellow', FAILED: 'badge-red' }
  return <span className={`badge ${m[status] || 'badge-gray'}`}>{status}</span>
}

function PipelineBadge({ status }) {
  const m = { created: 'badge-blue', completed: 'badge-green', failed: 'badge-red' }
  return <span className={`badge ${m[status] || 'badge-gray'}`}>{status}</span>
}

function fmtBytes(n) {
  if (!n) return '–'
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}

function fmtDate(ts) {
  if (!ts) return '–'
  return new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
