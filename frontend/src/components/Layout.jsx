import { NavLink, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

const NAV = [
  { to: '/',          icon: '⬡', label: 'Dashboard' },
  { to: '/datasets',  icon: '⊞', label: 'Datasets' },
  { to: '/upload',    icon: '↑', label: 'Upload' },
  { to: '/discussion', icon: '💬', label: 'Discussion' },
]

export default function Layout() {
  const [health, setHealth] = useState(null)
  const demo = health?.demo_mode ?? true

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
  }, [])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="brand">Kristik<br /><span>Engineering Copilot</span></div>
          <div className="version">v1.0.0</div>
        </div>

        <nav className="sidebar-nav">
          {NAV.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              className={({ isActive }) => isActive ? 'active' : ''}
            >
              <span className="nav-icon">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          {demo
            ? '⚠ Demo Mode — LLM not configured'
            : `● LLM: ${health?.llm_provider}${health?.llm_model ? ' · ' + health.llm_model : ''}`}
        </div>
      </aside>

      <main className="main-content">
        {demo && (
          <div className="demo-banner">
            ⚠ Demo Mode — AI recommendations are deterministic (no LLM API key configured)
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}
