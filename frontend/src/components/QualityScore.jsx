function scoreColor(s) {
  if (s >= 80) return 'var(--accent)'
  if (s >= 60) return 'var(--yellow)'
  return 'var(--red)'
}

export default function QualityScore({ score, breakdown }) {
  const color = scoreColor(score ?? 0)

  return (
    <div style={{ display: 'flex', gap: '2rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
      {/* Big score */}
      <div className="score-ring">
        <div className="score-value" style={{ color }}>{score ?? '–'}</div>
        <div className="score-label">/ 100</div>
        <div style={{ fontSize: '.7rem', color: 'var(--text-muted)', marginTop: '.25rem' }}>
          {score >= 80 ? 'Good' : score >= 60 ? 'Fair' : 'Poor'}
        </div>
      </div>

      {/* Breakdown bars */}
      {breakdown && (
        <div style={{ flex: 1, minWidth: 220 }}>
          {Object.entries(breakdown).map(([key, val]) => {
            const max = { missing_values: 30, duplicates: 20, outliers: 15, inconsistent_categories: 15, invalid_dates: 10, type_anomalies: 10 }[key] ?? 10
            const pct = Math.round((val / max) * 100)
            const barColor = pct >= 80 ? 'var(--accent)' : pct >= 50 ? 'var(--yellow)' : 'var(--red)'
            return (
              <div key={key} style={{ marginBottom: '.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.72rem', marginBottom: '.2rem' }}>
                  <span style={{ color: 'var(--text-muted)', textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</span>
                  <span style={{ color: 'var(--text)', fontWeight: 600 }}>{val.toFixed(1)} / {max}</span>
                </div>
                <div className="progress-bar-wrap">
                  <div className="progress-bar" style={{ width: `${pct}%`, background: barColor }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
