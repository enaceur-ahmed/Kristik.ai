import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api } from '../api/client'

export default function BenchmarkPage() {
  const { ds } = useOutletContext()
  const [results, setResults] = useState(null)
  const [running, setRunning] = useState(false)
  const [error,   setError]   = useState(null)

  const run = async () => {
    setRunning(true); setError(null); setResults(null)
    try {
      const r = await api.runBenchmark(ds.id)
      setResults(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', flexWrap: 'wrap', gap: '.5rem' }}>
        <div>
          <h2>Benchmark</h2>
          <div style={{ fontSize: '.8rem', color: 'var(--text-muted)', marginTop: '.2rem' }}>
            Compare Deterministic, AI, and AI+Critic+Validation modes
          </div>
        </div>
        <button className="btn btn-blue" onClick={run} disabled={running}>
          {running
            ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Running benchmark…</>
            : '▶ Run Benchmark'}
        </button>
      </div>

      {/* Methodology note */}
      <div className="alert alert-info mb-md" style={{ fontSize: '.78rem' }}>
        <strong>Methodology:</strong> All three modes run on the same dataset in sequence.
        Results are computed from actual execution — never fabricated.
        Demo mode uses deterministic recommendations for reproducibility.
      </div>

      {error   && <div className="alert alert-error">{error}</div>}

      {/* LLM fallback warning — any AI mode that fell back to deterministic recs */}
      {results && (results.mode_b?.llm_fallback || results.mode_c?.llm_fallback) && (
        <div className="alert alert-warning">
          ⚠ LLM call failed during benchmark — affected modes used deterministic
          recommendations instead. Check the LLM configuration.
        </div>
      )}

      {!results && !running && (
        <div className="empty-state">
          <div className="es-icon">⊡</div>
          <div className="es-title">No benchmark results yet</div>
          <div className="es-sub">Click Run Benchmark to compare the three pipeline modes</div>
        </div>
      )}

      {running && (
        <div className="loading-row">
          <div className="spinner" />
          Running all three modes — this may take a few seconds…
        </div>
      )}

      {results && (
        <>
          {/* Baseline */}
          <div className="card mb-md">
            <div className="card-header"><span className="card-title">Baseline</span></div>
            <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', fontSize: '.85rem' }}>
              <MetricItem label="Quality Score Before" value={results.baseline_quality_score?.toFixed(1)} unit="/100" />
              <MetricItem label="Total Issues Detected" value={results.total_issues_detected} />
            </div>
          </div>

          {/* Mode cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
            {[
              { key: 'mode_a', color: 'var(--blue-light)',   icon: 'A' },
              { key: 'mode_b', color: 'var(--yellow-light)', icon: 'B' },
              { key: 'mode_c', color: 'var(--accent)',        icon: 'C' },
            ].map(({ key, color, icon }) => {
              const m = results[key]
              if (!m) return null
              const improvement = m.quality_score_after != null && m.quality_score_before != null
                ? (m.quality_score_after - m.quality_score_before).toFixed(1)
                : null
              return (
                <div key={key} className="card" style={{ borderTop: `3px solid ${color}` }}>
                  <div style={{ display: 'flex', gap: '.75rem', alignItems: 'center', marginBottom: '1rem' }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: color, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '.9rem', flexShrink: 0 }}>
                      {icon}
                    </div>
                    <div>
                      <div style={{ fontWeight: 700 }}>{m.name}</div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.6rem', fontSize: '.8rem' }}>
                    <MetricItem label="Execution Time" value={`${m.execution_time_s}s`} />
                    <MetricItem label="Steps Applied" value={m.steps_applied} />
                    <MetricItem label="Issues Resolved" value={m.issues_resolved} />
                    <MetricItem label="Score Before" value={m.quality_score_before?.toFixed(1)} unit="/100" />
                    <MetricItem label="Score After" value={m.quality_score_after?.toFixed(1)} unit="/100" color={color} />
                    <MetricItem label="Score Δ" value={improvement != null ? `${improvement > 0 ? '+' : ''}${improvement}` : '–'} color={improvement > 0 ? 'var(--accent)' : 'var(--red-light)'} />
                    <MetricItem label="Validation" value={m.validation_status} color={m.validation_status === 'PASS' ? 'var(--accent)' : m.validation_status === 'WARNING' ? 'var(--yellow-light)' : 'var(--red-light)'} />
                    <MetricItem label="Failures" value={m.validation_failures} color={m.validation_failures > 0 ? 'var(--red-light)' : 'var(--accent)'} />
                    {m.recommendations_generated != null && (
                      <MetricItem label="Recs Generated" value={m.recommendations_generated} />
                    )}
                    {m.recommendations_rejected_by_critic != null && (
                      <MetricItem label="Critic Rejected" value={m.recommendations_rejected_by_critic} color="var(--yellow-light)" />
                    )}
                    {m.llm_fallback && (
                      <MetricItem label="LLM Fallback" value="yes — demo recs used" color="var(--yellow-light)" />
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Comparison table */}
          <div className="card mt-md">
            <div className="card-header"><span className="card-title">Side-by-Side Comparison</span></div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th style={{ color: 'var(--blue-light)' }}>Mode A — Deterministic</th>
                    <th style={{ color: 'var(--yellow-light)' }}>Mode B — AI Engineer</th>
                    <th style={{ color: 'var(--accent)' }}>Mode C — AI + Critic</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Quality Score After', m => m.quality_score_after?.toFixed(1)],
                    ['Execution Time (s)',  m => m.execution_time_s],
                    ['Steps Applied',       m => m.steps_applied],
                    ['Issues Resolved',     m => m.issues_resolved],
                    ['Validation Status',   m => m.validation_status],
                    ['Validation Failures', m => m.validation_failures],
                  ].map(([label, fn]) => (
                    <tr key={label}>
                      <td style={{ fontWeight: 600, color: 'var(--text-muted)' }}>{label}</td>
                      {['mode_a', 'mode_b', 'mode_c'].map(k => (
                        <td key={k} style={{ fontFamily: 'var(--font-mono)' }}>{fn(results[k]) ?? '–'}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function MetricItem({ label, value, unit = '', color }) {
  return (
    <div>
      <div style={{ fontSize: '.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: '.15rem' }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: '.9rem', color: color || 'var(--text)' }}>
        {value ?? '–'}{unit}
      </div>
    </div>
  )
}
