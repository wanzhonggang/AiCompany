import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { Dashboard } from './pages/Dashboard'
import { Agents } from './pages/Agents'
import { AgentChat } from './pages/AgentChat'
import { useState } from 'react'

function Sidebar() {
  const location = useLocation()
  const links = [
    { to: '/', label: '📊 控制台', exact: true },
    { to: '/agents', label: '🤖 AI 员工', exact: false },
  ]

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">🤖 AI 员工平台</div>
      <nav className="sidebar-nav">
        {links.map(l => (
          <Link
            key={l.to}
            to={l.to}
            className={`sidebar-link ${l.exact ? (location.pathname === '/' ? 'active' : '') : location.pathname.startsWith(l.to) ? 'active' : ''}`}
          >
            {l.label}
          </Link>
        ))}
      </nav>
    </aside>
  )
}

export default function App() {
  const [toast, setToast] = useState<{ message: string; type: string } | null>(null)

  const showToast = (message: string, type: string = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard showToast={showToast} />} />
            <Route path="/agents" element={<Agents showToast={showToast} />} />
            <Route path="/agents/:id/chat" element={<AgentChat showToast={showToast} />} />
          </Routes>
        </main>
      </div>
      {toast && (
        <div className="toast-container">
          <div className={`toast ${toast.type}`}>{toast.message}</div>
        </div>
      )}
    </BrowserRouter>
  )
}
