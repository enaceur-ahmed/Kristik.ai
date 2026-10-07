import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'

const SEV_COLOR = { low: 'badge-blue', medium: 'badge-yellow', high: 'badge-red', critical: 'badge-red' }
const RISK_COLOR = { low: 'badge-green', medium: 'badge-yellow', high: 'badge-red' }

export default function AIEngineerPage() {
  const { ds } = useOutletContext()
  const [recs,    setRecs]    = useState([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error,   setError]   = useState(null)
  const [filter,  setFilter]  = useState('all')
  const [llmFallback, setLlmFallback] = useState(false)
  const [llmError,    setLlmError]    = useState(null)
  const [llmModel,    setLlmModel]    = useState(null)

  const load = () => {
    setLoading(true)
    api.getRecs(ds.id)
      .then(setRecs)
      .catch(() => setRecs([]))
      .finally(() => setLoading(false))
  }

  useEffect(load, [ds.id])

  const generate = async () => {
    setRunning(true); setError(null)
    try {
      const r = await api.generateRecs(ds.id)
      setRecs(r.recommendations ?? [])
      setLlmFallback(!!r.llm_fallback)
      setLlmError(r.llm_error ?? null)
      setLlmModel(r.model ?? null)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  const act = async (recId, action) => {
    try {
      const updated = await api.updateRec(ds.id, recId, action)
      setRecs(rs => rs.map(r => r.id === recId ? updated : r))
    } catch (e) {
      alert(e.message)
    }
  }

  const applyAll = async () => {
    const pending = recs.filter(r => r.status === 'pending')
    for (const r of pending) await act(r.id, 'apply')
  }

  if (loading) return <div className="loading-row"><div className="spinner" />Loading recommendations…</div>

  const filtered = filter === 'all' ? recs : recs.filter(r => r.status === filter)
  const counts = { all: recs.length, pending: recs.filter(r => r.status === 'pending').length, applied: recs.filter(r => r.status === 'applied').length, rejected: recs.filter(r => r.status === 'rejected').length }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', flexWrap: 'wrap', gap: '.5rem' }}>
        <div>
          <h2>AI Data Engineer</h2>
          <div style={{ fontSize: '.8rem', color: 'var(--text-muted)', marginTop: '.2rem' }}>
            AI-generated recommendations based on profiling results
            {llmModel && <span> · model: <code>{llmModel}</code></span>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
          {counts.pending > 0 && (
            <button className="btn btn-primary" onClick={applyAll}>✓ Apply All ({counts.pending})</button>
          )}
          <button className="btn btn-blue" onClick={generate} disabled={running}>
            {running ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Generating…</> : '✦ Generate'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {/* LLM fallback warning — real provider failed, deterministic recs shown */}
      {llmFallback && (
        <div className="alert alert-warning">
          ⚠ LLM call failed — showing deterministic (rule-based) recommendations instead.
          {llmError && <span> Error: {llmError}</span>}
        </div>
      )}

      {/* Filter tabs */}
      {recs.length > 0 && (
        <div className="tabs">
          {['all', 'pending', 'applied', 'rejected'].map(f => (
            <button key={f} className={`tab ${filter === f ? 'active' : ''}`} onClick={() => setFilter(f)}>
              {f.charAt(0).toUpperCase() + f.slice(1)} ({counts[f]})
            </button>
          ))}
        </div>
      )}

      {recs.length === 0 ? (
        <div className="empty-state">
          <div className="es-icon">✦</div>
          <div className="es-title">No recommendations yet</div>
          <div className="es-sub">Run profiling and quality analysis first, then click Generate</div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <div className="es-sub">No {filter} recommendations</div>
        </div>
      ) : (
        filtered.map(rec => (
          <RecCard key={rec.id} rec={rec} onApply={() => act(rec.id, 'apply')} onReject={() => act(rec.id, 'reject')} />
        ))
      )}
    </div>
  )
}

function RecCard({ rec, onApply, onReject }) {
  const critic = rec.critic_review_json
  const statusClass = rec.status !== 'pending' ? rec.status : ''

  return (
    <div className={`rec-card ${statusClass}`}>
      <div className="rec-header">
        <div>
          <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '.3rem' }}>
            <span className={`badge ${SEV_COLOR[rec.severity] || 'badge-gray'}`}>{rec.severity}</span>
            <span className="badge badge-gray" style={{ fontSize: '.68rem' }}>{rec.issue}</span>
            {rec.column_name && (
              <code style={{ fontSize: '.75rem', background: 'var(--bg)', padding: '.1rem .35rem', borderRadius: 3 }}>
                {rec.column_name}
              </code>
            )}
          </div>
          <div className="rec-title">
            {actionLabel(rec.action)}{rec.strategy ? ` (${rec.strategy})` : ''}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '.4rem', alignItems: 'center' }}>
          {rec.status !== 'pending' && (
            <span className={`badge ${rec.status === 'applied' ? 'badge-green' : 'badge-gray'}`}>
              {rec.status}
            </span>
          )}
        </div>
      </div>

      {rec.reason && <div className="rec-reason">{rec.reason}</div>}
      {rec.expected_impact && <div className="rec-impact">↗ {rec.expected_impact}</div>}

      {/* Critic review */}
      {critic && (
        <div style={{
          marginTop: '.6rem',
          padding: '.5rem .75rem',
          background: 'var(--bg)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--border-light)',
          fontSize: '.75rem',
        }}>
          <div style={{ display: 'flex', gap: '.5rem', alignItems: 'center', marginBottom: '.25rem' }}>
            <span style={{ color: 'var(--text-muted)' }}>Critic Review:</span>
            <span className={`badge ${RISK_COLOR[critic.risk] || 'badge-gray'}`}>risk: {critic.risk}</span>
            <span className={`badge ${critic.status === 'accepted' ? 'badge-green' : critic.status === 'rejected' ? 'badge-red' : 'badge-yellow'}`}>
              {critic.status}
            </span>
          </div>
          <div style={{ color: 'var(--text-muted)' }}>{critic.reason}</div>
          {critic.alternative && (
            <div style={{ color: 'var(--teal-light)', marginTop: '.2rem' }}>💡 {critic.alternative}</div>
          )}
        </div>
      )}

      {rec.status === 'pending' && (
        <div className="rec-actions">
          <button className="btn btn-primary btn-sm" onClick={onApply}>✓ Apply</button>
          <button className="btn btn-danger btn-sm" onClick={onReject}>✕ Reject</button>
        </div>
      )}
    </div>
  )
}

function actionLabel(action) {
  const map = {
    fill_missing:            'Fill Missing Values',
    remove_duplicates:       'Remove Duplicates',
    clip_outliers:           'Clip Outliers',
    standardise_categories:  'Standardise Categories',
    parse_dates:             'Parse Dates',
    drop_column:             'Drop Column',
    cast_numeric:            'Cast to Numeric',
    drop_high_missing:       'Drop High-Missing Columns',
  }
  return map[action] || action
}
