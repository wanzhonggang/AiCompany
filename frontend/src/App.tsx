import { useEffect, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { changeMyPassword, clearToken, getMe, getStoredToken, type AuthResult, type AuthUser } from './api/client'
import { Dashboard } from './pages/Dashboard'
import { Agents } from './pages/Agents'
import { AgentChat } from './pages/AgentChat'
import { Office } from './pages/Office'
import { TaskManagement } from './pages/TaskManagement'
import { ModelManagement } from './pages/ModelManagement'
import { DepartmentManagement } from './pages/DepartmentManagement'
import { Entry } from './pages/Entry'
import { AdminManagement } from './pages/AdminManagement'
import { AuditLogs } from './pages/AuditLogs'

function Sidebar({ onLogout, onPassword }: { onLogout: () => void; onPassword: () => void }) {
  const location = useLocation()
  const links = [
    { to: '/', label: '📊 控制台', exact: true },
    { to: '/office', label: '🏢 AI办公室', exact: false },
    { to: '/agents', label: '🤖 AI 员工', exact: false },
    { to: '/departments', label: '🏬 部门管理', exact: false },
    { to: '/tasks', label: '📋 任务管理', exact: false },
    { to: '/models', label: '🧠 模型管理', exact: false },
    { to: '/admins', label: '🛡 管理员管理', exact: false },
    { to: '/audit', label: '🧾 操作记录', exact: false },
  ]
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <img className="brand-logo" src="/logo.svg" alt="AI 员工平台" />
        <span>AI 员工平台</span>
      </div>
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
      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button className="btn btn-ghost btn-sm" onClick={onPassword}>修改密码</button>
        <button className="btn btn-ghost btn-sm" onClick={onLogout}>退出登录</button>
      </div>
    </aside>
  )
}

export default function App() {
  const [toast, setToast] = useState<{ message: string; type: string } | null>(null)
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [passwordModalOpen, setPasswordModalOpen] = useState(false)
  const [passwordForm, setPasswordForm] = useState({ old_password: '', new_password: '' })

  const showToast = (message: string, type: string = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  const onAuthenticated = (result: AuthResult) => {
    setCurrentUser(result.user)
  }

  const logout = () => {
    clearToken()
    setCurrentUser(null)
    showToast('已退出登录', 'success')
  }

  const submitPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (passwordForm.new_password.length < 6) {
      showToast('新密码至少 6 位', 'error')
      return
    }
    try {
      await changeMyPassword(passwordForm.old_password, passwordForm.new_password)
      setPasswordModalOpen(false)
      setPasswordForm({ old_password: '', new_password: '' })
      showToast('管理员密码已修改', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '修改密码失败', 'error')
    }
  }

  useEffect(() => {
    const token = getStoredToken()
    if (!token) {
      setAuthLoading(false)
      return
    }
    getMe()
      .then(user => setCurrentUser(user))
      .catch(() => {
        clearToken()
        setCurrentUser(null)
      })
      .finally(() => setAuthLoading(false))
  }, [])

  if (authLoading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  if (!currentUser) {
    return (
      <>
        <Entry onAuthenticated={onAuthenticated} showToast={showToast} />
        {toast && (
          <div className="toast-container">
            <div className={`toast ${toast.type}`}>{toast.message}</div>
          </div>
        )}
      </>
    )
  }

  if (currentUser.role === 'employee') {
    if (!currentUser.agent_id) {
      return (
        <div style={{ padding: 40 }}>
          <div className="page-title">员工账号未绑定 AI 员工</div>
          <button className="btn btn-ghost btn-sm" onClick={logout}>退出登录</button>
        </div>
      )
    }
    return (
      <BrowserRouter>
        <div className="app-layout" style={{ display: 'block' }}>
          <main className="main-content" style={{ marginLeft: 0 }}>
            <div className="page-header">
              <div>
                <h1 className="page-title">员工工作台</h1>
                <div className="office-subtitle">{currentUser.display_name} · {currentUser.enterprise_name}</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={logout}>退出登录</button>
            </div>
            <Routes>
              <Route
                path="/agents/:id/chat"
                element={<AgentChat showToast={showToast} readOnlyProfile />}
              />
              <Route
                path="*"
                element={<Navigate to={`/agents/${currentUser.agent_id}/chat`} replace />}
              />
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

  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar onLogout={logout} onPassword={() => setPasswordModalOpen(true)} />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard showToast={showToast} enterpriseName={currentUser.enterprise_name} />} />
            <Route path="/office" element={<Office showToast={showToast} />} />
            <Route path="/agents" element={<Agents showToast={showToast} />} />
            <Route path="/departments" element={<DepartmentManagement showToast={showToast} />} />
            <Route path="/tasks" element={<TaskManagement showToast={showToast} />} />
            <Route path="/models" element={<ModelManagement showToast={showToast} />} />
            <Route path="/admins" element={<AdminManagement showToast={showToast} />} />
            <Route path="/audit" element={<AuditLogs showToast={showToast} />} />
            <Route path="/agents/:id/chat" element={<AgentChat showToast={showToast} />} />
          </Routes>
        </main>
      </div>
      {toast && (
        <div className="toast-container">
          <div className={`toast ${toast.type}`}>{toast.message}</div>
        </div>
      )}
      {passwordModalOpen && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setPasswordModalOpen(false) }}>
          <div className="modal-content" style={{ maxWidth: 420 }}>
            <div className="modal-header">
              <h3 className="modal-title">修改管理员密码</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setPasswordModalOpen(false)}>关闭</button>
            </div>
            <form onSubmit={submitPassword} className="task-form">
              <label>
                <span>原密码</span>
                <input className="form-input" type="password" value={passwordForm.old_password} onChange={e => setPasswordForm({ ...passwordForm, old_password: e.target.value })} />
              </label>
              <label>
                <span>新密码</span>
                <input className="form-input" type="password" value={passwordForm.new_password} onChange={e => setPasswordForm({ ...passwordForm, new_password: e.target.value })} />
              </label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setPasswordModalOpen(false)}>取消</button>
                <button type="submit" className="btn btn-primary">保存密码</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </BrowserRouter>
  )
}
