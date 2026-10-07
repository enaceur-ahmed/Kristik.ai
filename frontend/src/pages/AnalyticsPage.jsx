import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import MiniBarChart from '../components/MiniBarChart'

export default function AnalyticsPage() {
  const { ds } = useOutletContext()
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [tab,     setTab]     = useState('stats')

  useEffect(() => {
    setLoading(true)
    api.getAnalytics(ds.id)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [ds.id])

  if (loading) return <div className="loading-row"><div className="spinner" />Computing analytics…</div>
  if (error)   return <div className="alert alert-error">{error}</div>
  if (!data)   return <div className="empty-state"><div className="es-sub">No analytics available</div></div>

  return (
    <div>
      <h2 style={{ marginBottom: '1rem' }}>Analytics</h2>

      <div className="tabs">
        {['stats', 'distributions', 'correlations', 'categorical', 'insights'].map(t => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === 'stats'        && <DescriptiveStats stats={data.descriptive_stats} />}
      {tab === 'distributions' && <Distributions dists={data.distributions} />}
      {tab === 'correlations'  && <Correlations corr={data.correlations} top={data.top_correlations} />}
      {tab === 'categorical'   && <CategoricalSummaries summaries={data.categorical_summaries} />}
      {tab === 'insights'      && <Insights insights={data.insights} timeSeries={data.time_series} />}
    </div>
  )
}

/* ---- Descriptive Stats ---- */
function DescriptiveStats({ stats }) {
  if (!stats || !Object.keys(stats).length)
    return <div className="empty-state"><div className="es-sub">No numerical columns</div></div>

  const statKeys = ['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']

  return (
    <div className="card">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Statistic</th>
              {Object.keys(stats).map(c => <th key={c} style={{ fontFamily: 'var(--font-mono)' }}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {statKeys.map(sk => (
              <tr key={sk}>
                <td style={{ fontWeight: 600, color: 'var(--text-muted)' }}>{sk}</td>
                {Object.values(stats).map((col, i) => (
                  <td key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: '.8rem' }}>
                    {fmt(col[sk])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ---- Distributions ---- */
function Distributions({ dists }) {
  if (!dists || !Object.keys(dists).length)
    return <div className="empty-state"><div className="es-sub">No distributions available</div></div>

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
      {Object.entries(dists).map(([col, dist]) => (
        <div key={col} className="card">
          <div className="card-header">
            <span className="card-title" style={{ fontFamily: 'var(--font-mono)' }}>{col}</span>
            <span style={{ fontSize: '.7rem', color: 'var(--text-muted)' }}>Distribution</span>
          </div>
          <Histogram counts={dist.counts} binEdges={dist.bin_edges} />
        </div>
      ))}
    </div>
  )
}

function Histogram({ counts = [], binEdges = [] }) {
  const max = Math.max(...counts, 1)
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 80 }}>
      {counts.map((c, i) => {
        const h = Math.round((c / max) * 70)
        const label = binEdges[i] != null ? binEdges[i].toFixed(1) : ''
        return (
          <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }} title={`${label}: ${c}`}>
            <div style={{ width: '100%', height: h, background: 'var(--blue)', borderRadius: '2px 2px 0 0', minHeight: 1 }} />
          </div>
        )
      })}
    </div>
  )
}

/* ---- Correlations ---- */
function Correlations({ corr, top }) {
  const cols = Object.keys(corr || {})
  if (!cols.length) return <div className="empty-state"><div className="es-sub">Need ≥2 numerical columns</div></div>

  return (
    <div style={{ display: 'grid', gridTemplateColumns: top?.length ? '1fr 1fr' : '1fr', gap: '1rem' }}>
      {/* Heatmap */}
      <div className="card">
        <div className="card-header"><span className="card-title">Correlation Matrix</span></div>
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
                    const bg = v == null ? 'transparent'
                      : abs > 0.7 ? (v > 0 ? '#DCFCE7' : '#FFEBE9')
                      : abs > 0.4 ? (v > 0 ? '#DDF4FF' : '#FFF8C5')
                      : 'transparent'
                    return (
                      <td key={col} style={{ background: bg, textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '.75rem' }}>
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

      {/* Top correlations */}
      {top?.length > 0 && (
        <div className="card">
          <div className="card-header"><span className="card-title">Strongest Correlations</span></div>
          {top.slice(0, 8).map((pair, i) => {
            const abs = Math.abs(pair.correlation)
            const color = abs > 0.7 ? 'var(--accent)' : abs > 0.4 ? 'var(--yellow-light)' : 'var(--text-muted)'
            return (
              <div key={i} style={{ marginBottom: '.6rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.78rem', marginBottom: '.2rem' }}>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{pair.col1} ↔ {pair.col2}</span>
                  <span style={{ fontWeight: 700, color }}>{pair.correlation.toFixed(3)}</span>
                </div>
                <div className="progress-bar-wrap">
                  <div className="progress-bar" style={{ width: `${abs * 100}%`, background: color }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ---- Categorical Summaries ---- */
function CategoricalSummaries({ summaries }) {
  if (!summaries || !Object.keys(summaries).length)
    return <div className="empty-state"><div className="es-sub">No categorical columns</div></div>

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
      {Object.entries(summaries).map(([col, s]) => (
        <div key={col} className="card">
          <div className="card-header">
            <span className="card-title" style={{ fontFamily: 'var(--font-mono)' }}>{col}</span>
            <span style={{ fontSize: '.7rem', color: 'var(--text-muted)' }}>{s.unique_count} unique</span>
          </div>
          <MiniBarChart data={s.top_values || []} colorVar="var(--purple-light)" />
        </div>
      ))}
    </div>
  )
}

/* ---- Insights ---- */
function Insights({ insights, timeSeries }) {
  return (
    <div>
      <div className="card mb-md">
        <div className="card-header"><span className="card-title">Business Insights</span></div>
        {insights?.length ? (
          <ul style={{ paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '.5rem' }}>
            {insights.map((ins, i) => (
              <li key={i} style={{ fontSize: '.85rem', color: 'var(--text)' }}>{ins}</li>
            ))}
          </ul>
        ) : (
          <div className="text-muted" style={{ fontSize: '.8rem' }}>No insights available.</div>
        )}
      </div>

      {timeSeries && Object.keys(timeSeries).length > 0 && (
        <div className="card">
          <div className="card-header"><span className="card-title">Time Series</span></div>
          {Object.entries(timeSeries).map(([key, ts]) => (
            <div key={key} style={{ marginBottom: '1rem' }}>
              <div style={{ fontSize: '.8rem', fontWeight: 600, marginBottom: '.5rem', fontFamily: 'var(--font-mono)' }}>{key}</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 60, overflow: 'hidden' }}>
                {(ts.values || []).map((v, i) => {
                  const max = Math.max(...ts.values.filter(Boolean), 1)
                  const h = Math.round(((v || 0) / max) * 55)
                  return (
                    <div key={i} title={`${ts.dates?.[i]}: ${v}`} style={{ flex: 1, height: h, background: 'var(--teal)', borderRadius: '2px 2px 0 0', minHeight: 1 }} />
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function fmt(v) {
  if (v == null) return '–'
  if (typeof v === 'number') return Math.abs(v) >= 1000 ? v.toLocaleString() : v.toFixed(3)
  return v
}
