import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'
import LogStream from '../components/LogStream'

const OP_LABELS = {
  remove_duplicates:      'Remove Duplicates',
  fill_missing:           'Fill Missing',
  clip_outliers:          'Clip Outliers',
  standardise_categories: 'Standardise Categories',
  parse_dates:            'Parse Dates',
  drop_column:            'Drop Column',
  cast_numeric:           'Cast Numeric',
  drop_high_missing:      'Drop High-Missing',
}

export default function PipelinePage() {
  const { ds } = useOutletContext()
  const [pipelines, setPipelines] = useState([])
  const [logs,      setLogs]      = useState([])
  const [loading,   setLoading]   = useState(true)
  const [genBusy,   setGenBusy]   = useState(false)
  const [execBusy,  setExecBusy]  = useState(false)
  const [error,     setError]     = useState(null)
  const [selected,  setSelected]  = useState(null)
  const [codeOpen,  setCodeOpen]  = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([api.getPipelines(ds.id), api.getLogs(ds.id)])
      .then(([ps, ls]) => {
        setPipelines(ps)
        setLogs(ls)
        if (ps.length > 0 && !selected) setSelected(ps[0])
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [ds.id])

  const generate = async () => {
    setGenBusy(true); setError(null)
    try {
      const p = await api.generatePipeline(ds.id)
      const ls = await api.getLogs(ds.id)
      setPipelines(prev => [p, ...prev.filter(x => x.id !== p.id)])
      setSelected(p)
      setLogs(ls)
    } catch (e) { setError(e.message) }
    finally { setGenBusy(false) }
  }

  const execute = async () => {
    if (!selected) return
    setExecBusy(true); setError(null)
    try {
      const p = await api.executePipeline(ds.id, selected.id)
      const ls = await api.getLogs(ds.id)
      setPipelines(prev => prev.map(x => x.id === p.id ? p : x))
      setSelected(p)
      setLogs(ls)
    } catch (e) { setError(e.message) }
    finally { setExecBusy(false) }
  }

  if (loading) return <div className="loading-row"><div className="spinner" />Loading pipelines…</div>

  const active = selected || pipelines[0] || null

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', flexWrap: 'wrap', gap: '.5rem' }}>
        <div>
          <h2>Pipeline Builder</h2>
          <div style={{ fontSize: '.8rem', color: 'var(--text-muted)', marginTop: '.2rem' }}>
            Generate and execute transformation pipelines
          </div>
        </div>
        <div style={{ display: 'flex', gap: '.5rem' }}>
          <button className="btn btn-blue" onClick={generate} disabled={genBusy}>
            {genBusy ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Generating…</> : '⊞ Generate Pipeline'}
          </button>
          {active && active.status === 'created' && (
            <button className="btn btn-primary" onClick={execute} disabled={execBusy}>
              {execBusy ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Executing…</> : '▶ Execute'}
            </button>
          )}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {!active ? (
        <div className="empty-state">
          <div className="es-icon">⊟</div>
          <div className="es-title">No pipeline yet</div>
          <div className="es-sub">Apply recommendations in the AI Engineer tab, then generate a pipeline</div>
        </div>
      ) : (
        <>
          {/* Pipeline selector */}
          {pipelines.length > 1 && (
            <div style={{ display: 'flex', gap: '.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
              {pipelines.map(p => (
                <button
                  key={p.id}
                  className={`btn ${selected?.id === p.id ? 'btn-blue' : 'btn-ghost'} btn-sm`}
                  onClick={() => setSelected(p)}
                >
                  {p.name} <StatusDot status={p.status} />
                </button>
              ))}
            </div>
          )}

          {/* Pipeline info */}
          <div className="card mb-md">
            <div className="card-header">
              <span className="card-title" style={{ fontFamily: 'var(--font-mono)' }}>{active.name}</span>
              <div style={{ display: 'flex', gap: '.75rem', alignItems: 'center' }}>
                {active.execution_time_s && (
                  <span style={{ fontSize: '.75rem', color: 'var(--text-muted)' }}>
                    ⏱ {active.execution_time_s}s
                  </span>
                )}
                <PipelineStatusBadge status={active.status} />
              </div>
            </div>

            {/* Visual steps */}
            <div className="pipeline-steps">
              {active.steps_json.map((step, i) => {
                const result = step.result || {}
                const stepStatus = result.status || (active.status === 'completed' ? 'success' : 'pending')
                return (
                  <div key={i} className="pipeline-step">
                    <div
                      className={`pipeline-step-box status-${stepStatus}`}
                      title={result.message || ''}
                    >
                      <div style={{ fontSize: '.65rem', color: 'var(--text-faint)', marginBottom: 2 }}>
                        Step {step.step}
                      </div>
                      <div style={{ fontWeight: 600, fontSize: '.72rem' }}>
                        {OP_LABELS[step.operation] || step.operation}
                      </div>
                      {step.column && (
                        <div style={{ fontSize: '.65rem', color: 'inherit', marginTop: 2, fontFamily: 'var(--font-mono)' }}>
                          {step.column}
                        </div>
                      )}
                    </div>
                    {i < active.steps_json.length - 1 && (
                      <span className="pipeline-arrow">→</span>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Step details */}
            {active.status === 'completed' && (
              <div style={{ marginTop: '1rem' }}>
                <div style={{ fontSize: '.8rem', fontWeight: 600, marginBottom: '.5rem' }}>Step Results</div>
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Step</th><th>Operation</th><th>Column</th><th>Status</th><th>Message</th></tr></thead>
                    <tbody>
                      {active.steps_json.map((step, i) => {
                        const r = step.result || {}
                        return (
                          <tr key={i}>
                            <td>{step.step}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: '.75rem' }}>{step.operation}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: '.75rem', color: 'var(--text-muted)' }}>{step.column || '–'}</td>
                            <td>
                              {r.status === 'success' && <span className="badge badge-green">Success</span>}
                              {r.status === 'error'   && <span className="badge badge-red">Error</span>}
                              {r.status === 'skipped' && <span className="badge badge-gray">Skipped</span>}
                              {!r.status             && <span className="badge badge-gray">–</span>}
                            </td>
                            <td style={{ fontSize: '.75rem', color: 'var(--text-muted)' }}>{r.message || '–'}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* Generated code */}
          {active.generated_code && (
            <div className="card mb-md">
              <div className="card-header">
                <span className="card-title">Generated Python Code</span>
                <button className="btn btn-ghost btn-sm" onClick={() => setCodeOpen(o => !o)}>
                  {codeOpen ? '▲ Hide' : '▼ Show'}
                </button>
              </div>
              {codeOpen && (
                <>
                  <div style={{ fontSize: '.72rem', color: 'var(--text-muted)', marginBottom: '.5rem' }}>
                    ⚠ Review before executing. This code is generated for reference — the application uses a validated execution engine, not arbitrary code eval.
                  </div>
                  <pre style={{ maxHeight: 400, overflow: 'auto', fontSize: '.775rem' }}>
                    {active.generated_code}
                  </pre>
                  <button
                    className="btn btn-ghost btn-sm mt-sm"
                    onClick={() => navigator.clipboard.writeText(active.generated_code)}
                  >
                    ⎘ Copy to clipboard
                  </button>
                </>
              )}
            </div>
          )}
        </>
      )}

      {/* Logs */}
      <div className="card">
        <div className="card-header"><span className="card-title">Execution Log</span></div>
        <LogStream logs={logs} />
      </div>
    </div>
  )
}

function PipelineStatusBadge({ status }) {
  const map = {
    created:   ['badge-blue',   'Created'],
    running:   ['badge-yellow', 'Running'],
    completed: ['badge-green',  'Completed'],
    failed:    ['badge-red',    'Failed'],
  }
  const [cls, label] = map[status] || ['badge-gray', status]
  return <span className={`badge ${cls}`}>{label}</span>
}

function StatusDot({ status }) {
  const colors = { created: 'var(--blue-light)', completed: 'var(--accent)', failed: 'var(--red-light)' }
  return (
    <span style={{ width: 6, height: 6, borderRadius: '50%', background: colors[status] || 'var(--text-faint)', display: 'inline-block', marginLeft: 4 }} />
  )
}
