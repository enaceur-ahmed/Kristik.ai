import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import MiniBarChart from '../components/MiniBarChart'
import LogStream from '../components/LogStream'

export default function ProfilePage() {
  const { ds } = useOutletContext()
  const [profile, setProfile] = useState(null)
  const [logs, setLogs]       = useState([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError]     = useState(null)
  const [tab, setTab]         = useState('overview')

  const loadProfile = () => {
    setLoading(true)
    Promise.all([
      api.getProfile(ds.id).catch(() => null),
      api.getLogs(ds.id).catch(() => []),
    ]).then(([p, l]) => {
      setProfile(p)
      setLogs(l)
    }).finally(() => setLoading(false))
  }

  useEffect(loadProfile, [ds.id])

  const runProfile = async () => {
    setRunning(true); setError(null)
    try {
      const p = await api.runProfile(ds.id)
      const l = await api.getLogs(ds.id)
      setProfile(p); setLogs(l)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  if (loading) return <div className="loading-row"><div className="spinner" /> Loading profile…</div>

  const p = profile?.profile_json

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2>Dataset Overview</h2>
        <button className="btn btn-blue" onClick={runProfile} disabled={running}>
          {running ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Profiling…</> : '↺ Re-profile'}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {!p ? (
        <div className="empty-state">
          <div className="es-icon">⊞</div>
          <div className="es-title">No profile yet</div>
          <div className="es-sub">Click Re-profile to analyse this dataset</div>
        </div>
      ) : (
        <>
          {/* Summary stats */}
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
            <StatCard label="Rows"       value={p.rows?.toLocaleString()} />
            <StatCard label="Columns"    value={p.columns} />
            <StatCard label="Duplicates" value={`${p.duplicate_rows} (${p.duplicate_percentage}%)`} color={p.duplicate_percentage > 0 ? 'var(--yellow-light)' : undefined} />
            <StatCard label="Memory"     value={fmtBytes(p.memory_usage_bytes)} />
            <StatCard label="Num Cols"   value={p.numerical_columns?.length ?? 0} color="var(--blue-light)" />
            <StatCard label="Cat Cols"   value={p.categorical_columns?.length ?? 0} color="var(--purple-light)" />
            <StatCard label="Date Cols"  value={p.date_columns?.length ?? 0} color="var(--teal-light)" />
          </div>

          {/* Column tabs */}
          <div className="tabs" style={{ marginTop: '.5rem' }}>
            {['overview', 'numerical', 'categorical', 'missing', 'correlations', 'preview'].map(t => (
              <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>

          {tab === 'overview' && <OverviewTab p={p} />}
          {tab === 'numerical' && <NumericalTab p={p} />}
          {tab === 'categorical' && <CategoricalTab p={p} />}
          {tab === 'missing' && <MissingTab p={p} />}
          {tab === 'correlations' && <CorrelationsTab p={p} />}
          {tab === 'preview' && <PreviewTab ds={ds} />}
        </>
      )}

      {/* Execution log */}
      <div className="card mt-lg">
        <div className="card-header"><span className="card-title">Execution Log</span></div>
        <LogStream logs={logs} />
      </div>
    </div>
  )
}

function StatCard({ label, value, color }) {
  return (
    <div className="stat-card">
      <div className="label">{label}</div>
      <div className="value" style={{ fontSize: '1.2rem', color: color || 'var(--text)' }}>{value}</div>
    </div>
  )
}

function OverviewTab({ p }) {
  const cols = Object.entries(p.column_profiles || {})
  return (
    <div className="card">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Column</th><th>Type</th><th>Dtype</th><th>Unique</th><th>Missing</th><th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {cols.map(([col, cp]) => (
              <tr key={col}>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{col}</td>
                <td><ColTypeBadge type={cp.column_type} /></td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '.72rem', color: 'var(--text-muted)' }}>{cp.dtype}</td>
                <td>{cp.unique_count} <span style={{ color: 'var(--text-muted)' }}>({cp.unique_percentage}%)</span></td>
                <td>
                  {cp.null_percentage > 0
                    ? <span style={{ color: cp.null_percentage > 20 ? 'var(--red-light)' : 'var(--yellow-light)' }}>
                        {cp.null_percentage}%
                      </span>
                    : <span style={{ color: 'var(--accent)' }}>✓</span>}
                </td>
                <td style={{ fontSize: '.72rem', color: 'var(--text-muted)' }}>
                  {cp.likely_datetime && '📅 date-like strings '}
                  {cp.outlier_count > 0 && `⚠ ${cp.outlier_count} outliers `}
                  {cp.inconsistent_category_count > 0 && `⚠ ${cp.inconsistent_category_count} cat variants`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function NumericalTab({ p }) {
  const cols = (p.numerical_columns || []).map(c => [c, p.column_profiles[c]]).filter(([, cp]) => cp)
  if (!cols.length) return <div className="empty-state"><div className="es-sub">No numerical columns</div></div>
  return (
    <div className="card">
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Column</th><th>Min</th><th>Max</th><th>Mean</th><th>Median</th><th>Std</th><th>Skew</th><th>Outliers</th></tr>
          </thead>
          <tbody>
            {cols.map(([col, cp]) => (
              <tr key={col}>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{col}</td>
                <td>{fmt(cp.min)}</td><td>{fmt(cp.max)}</td><td>{fmt(cp.mean)}</td>
                <td>{fmt(cp.median)}</td><td>{fmt(cp.std)}</td>
                <td style={{ color: Math.abs(cp.skewness ?? 0) > 1 ? 'var(--yellow-light)' : 'inherit' }}>{fmt(cp.skewness)}</td>
                <td style={{ color: cp.outlier_count > 0 ? 'var(--red-light)' : 'var(--accent)' }}>
                  {cp.outlier_count ?? 0}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CategoricalTab({ p }) {
  const cols = (p.categorical_columns || []).map(c => [c, p.column_profiles[c]]).filter(([, cp]) => cp)
  if (!cols.length) return <div className="empty-state"><div className="es-sub">No categorical columns</div></div>
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
      {cols.map(([col, cp]) => (
        <div key={col} className="card">
          <div className="card-header">
            <span className="card-title" style={{ fontFamily: 'var(--font-mono)' }}>{col}</span>
            <span style={{ fontSize: '.7rem', color: 'var(--text-muted)' }}>{cp.unique_count} unique</span>
          </div>
          <MiniBarChart data={cp.top_values || []} colorVar="var(--purple-light)" />
          {cp.inconsistent_category_count > 0 && (
            <div style={{ fontSize: '.72rem', color: 'var(--yellow-light)', marginTop: '.5rem' }}>
              ⚠ {cp.inconsistent_category_count} inconsistent variants
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function MissingTab({ p }) {
  const missing = Object.entries(p.missing_values || {}).filter(([, v]) => v.percentage > 0)
  if (!missing.length) return (
    <div className="empty-state">
      <div className="es-icon" style={{ color: 'var(--accent)' }}>✓</div>
      <div className="es-title">No missing values</div>
    </div>
  )
  return (
    <div className="card">
      <div className="table-wrap">
        <table>
          <thead><tr><th>Column</th><th>Missing Count</th><th>Missing %</th><th>Severity</th></tr></thead>
          <tbody>
            {missing.sort((a, b) => b[1].percentage - a[1].percentage).map(([col, v]) => (
              <tr key={col}>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{col}</td>
                <td>{v.count.toLocaleString()}</td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem' }}>
                    <div className="progress-bar-wrap" style={{ width: 100 }}>
                      <div className="progress-bar" style={{
                        width: `${v.percentage}%`,
                        background: v.percentage > 50 ? 'var(--red)' : v.percentage > 20 ? 'var(--yellow)' : 'var(--blue-light)',
                      }} />
                    </div>
                    <span>{v.percentage}%</span>
                  </div>
                </td>
                <td><SeverityBadge pct={v.percentage} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CorrelationsTab({ p }) {
  const corr = p.correlation || {}
  const cols = Object.keys(corr)
  if (cols.length < 2) return <div className="empty-state"><div className="es-sub">Need at least 2 numerical columns for correlation</div></div>
  return (
    <div className="card">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              {cols.map(c => <th key={c} style={{ fontFamily: 'var(--font-mono)', fontSize: '.7rem' }}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {cols.map(row => (
              <tr key={row}>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '.75rem' }}>{row}</td>
                {cols.map(col => {
                  const v = corr[row]?.[col]
                  const abs = Math.abs(v ?? 0)
                  const color = v == null ? 'transparent'
                    : abs > 0.7 ? (v > 0 ? '#DCFCE7' : '#FFEBE9')
                    : abs > 0.4 ? (v > 0 ? '#DDF4FF' : '#FFF8C5')
                    : 'transparent'
                  return (
                    <td key={col} style={{ background: color, textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '.75rem' }}>
                      {v != null ? v.toFixed(2) : '–'}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ColTypeBadge({ type }) {
  const map = { numerical: 'badge-blue', categorical: 'badge-purple', datetime: 'badge-yellow' }
  return <span className={`badge ${map[type] || 'badge-gray'}`}>{type}</span>
}

function SeverityBadge({ pct }) {
  if (pct === 0)  return <span className="badge badge-green">None</span>
  if (pct < 5)    return <span className="badge badge-blue">Low</span>
  if (pct < 20)   return <span className="badge badge-yellow">Medium</span>
  if (pct < 50)   return <span className="badge badge-red">High</span>
  return <span className="badge badge-red">Critical</span>
}

function fmt(v) {
  if (v == null) return <span style={{ color: 'var(--text-faint)' }}>–</span>
  return typeof v === 'number' ? v.toFixed(3) : v
}

function fmtBytes(n) {
  if (!n) return '–'
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}

function PreviewTab({ ds }) {
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    api.getPreview(ds.id, 50)
      .then(data => {
        setPreview(data)
        setError(null)
      })
      .catch(err => {
        setError(err.message)
        setPreview(null)
      })
      .finally(() => setLoading(false))
  }, [ds.id])

  if (loading) return <div className="loading-row"><div className="spinner" /> Loading preview…</div>
  if (error) return <div className="alert alert-error">Failed to load preview: {error}</div>
  if (!preview) return <div className="empty-state"><div className="es-sub">No preview available</div></div>

  const { columns, rows, row_count, preview_rows, dataset_name, file_type } = preview

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <span className="card-title">Data Preview</span>
          <span style={{ fontSize: '.8rem', color: 'var(--text-muted)', marginLeft: '.5rem' }}>
            {preview_rows} of {row_count || '?'} rows • {columns.length} columns • {file_type}
          </span>
        </div>
        <div style={{ fontSize: '.8rem', color: 'var(--text-muted)' }}>
          Showing first {preview_rows} rows
        </div>
      </div>
      
      {rows.length === 0 ? (
        <div className="empty-state">
          <div className="es-sub">No data rows available for preview</div>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {columns.map(col => (
                  <th key={col} style={{ fontFamily: 'var(--font-mono)', fontSize: '.75rem' }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 50).map((row, idx) => (
                <tr key={idx}>
                  {columns.map(col => {
                    const val = row[col]
                    return (
                      <td key={col} style={{
                        fontSize: '.75rem',
                        fontFamily: typeof val === 'number' ? 'var(--font-mono)' : 'inherit',
                        color: val === null || val === undefined ? 'var(--text-faint)' : 'inherit'
                      }}>
                        {val === null || val === undefined ? (
                          <span style={{ color: 'var(--text-faint)' }}>–</span>
                        ) : typeof val === 'number' ? (
                          val.toLocaleString()
                        ) : typeof val === 'boolean' ? (
                          val.toString()
                        ) : (
                          String(val)
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
