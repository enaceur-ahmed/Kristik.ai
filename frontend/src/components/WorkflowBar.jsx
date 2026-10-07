const STEPS = [
  'Upload', 'Profile', 'Quality', 'AI Recs', 'Pipeline', 'Validate', 'Analytics'
]

export default function WorkflowBar({ current = 0, done = [] }) {
  return (
    <div className="workflow-bar">
      {STEPS.map((s, i) => {
        const isDone   = done.includes(i) || i < current
        const isActive = i === current
        return (
          <div key={s} className="workflow-step-wrap" style={{ display: 'flex', alignItems: 'center' }}>
            <div className={`workflow-step ${isDone ? 'done' : ''} ${isActive ? 'active' : ''}`}>
              <div className="ws-num">{isDone ? '✓' : i + 1}</div>
              <span className="ws-label">{s}</span>
            </div>
            {i < STEPS.length - 1 && <span className="workflow-sep">›</span>}
          </div>
        )
      })}
    </div>
  )
}
