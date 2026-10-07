/**
 * A simple horizontal bar chart for categorical distributions.
 * Uses plain CSS — no charting library dependency.
 */
export default function MiniBarChart({ data = [], colorVar = 'var(--blue-light)' }) {
  if (!data.length) return <div className="text-muted" style={{ fontSize: '.8rem' }}>No data</div>

  const max = Math.max(...data.map(d => d.count))

  return (
    <div className="bar-chart">
      {data.slice(0, 12).map(({ value, count, percentage }) => (
        <div key={value} className="bar-row">
          <span className="bar-label" title={value}>{value}</span>
          <div style={{ background: 'var(--bg)', borderRadius: 3, overflow: 'hidden', height: 8 }}>
            <div style={{
              width: `${(count / max) * 100}%`,
              height: '100%',
              background: colorVar,
              borderRadius: 3,
            }} />
          </div>
          <span className="bar-val">
            {percentage !== undefined ? `${percentage}%` : count}
          </span>
        </div>
      ))}
    </div>
  )
}
