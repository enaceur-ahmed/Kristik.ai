import { useEffect, useRef } from 'react'

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('en-GB', { hour12: false })
}

export default function LogStream({ logs = [] }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  if (!logs.length) return (
    <div className="log-stream">
      <span style={{ color: 'var(--text-faint)' }}>No log entries yet.</span>
    </div>
  )

  return (
    <div className="log-stream">
      {logs.map(l => (
        <div key={l.id} className="log-entry">
          <span className="ts">{fmtTime(l.created_at)}</span>
          <span className={`lvl-${l.level}`}>{l.level}</span>
          <span className="msg">{l.message}</span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  )
}
