import { useEffect, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { beginGlobalLoading, changeMyPassword, clearToken, getMe, getStoredToken, GLOBAL_LOADING_EVENT, type AuthResult, type AuthUser } from './api/client'
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

function Sidebar({ onSettings }: { onSettings: () => void }) {
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
      <div className="sidebar-settings">
        <button className="sidebar-settings-button" onClick={onSettings} aria-label="打开企业设置">
          ⚙
        </button>
      </div>
    </aside>
  )
}

function GlobalLoading({ message }: { message: string }) {
  return (
    <div className="global-loading-layer">
      <div className="global-loading-card">
        <div className="ai-spinner">
          <img src="/logo.svg" alt="" />
          <span />
        </div>
        <div>
          <strong>{message}</strong>
          <p>网络请求处理中，请稍候</p>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [toast, setToast] = useState<{ message: string; type: string } | null>(null)
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [globalLoading, setGlobalLoading] = useState<{ active: boolean; message: string }>({ active: false, message: '' })
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [passwordModalOpen, setPasswordModalOpen] = useState(false)
  const [passwordForm, setPasswordForm] = useState({ old_password: '', new_password: '' })

  const showToast = (message: string, type: string = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  const onAuthenticated = (result: AuthResult) => {
    setCurrentUser(result.user)
    if (result.user.role === 'admin') {
      window.history.replaceState(null, '', '/')
    } else if (result.user.agent_id) {
      window.history.replaceState(null, '', `/agents/${result.user.agent_id}/chat`)
    }
  }

  const logout = () => {
    clearToken()
    setSettingsOpen(false)
    setCurrentUser(null)
    showToast('已退出登录', 'success')
  }

  const openPasswordModal = () => {
    setSettingsOpen(false)
    setPasswordModalOpen(true)
  }

  const submitPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (passwordForm.new_password.length < 6) {
      showToast('新密码至少 6 位', 'error')
      return
    }
    const stopLoading = beginGlobalLoading('正在修改管理员密码...')
    try {
      await changeMyPassword(passwordForm.old_password, passwordForm.new_password)
      setPasswordModalOpen(false)
      setPasswordForm({ old_password: '', new_password: '' })
      showToast('管理员密码已修改', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '修改密码失败', 'error')
    } finally {
      stopLoading()
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

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ active: boolean; message: string }>).detail
      setGlobalLoading({ active: detail.active, message: detail.message || 'AI 正在处理中...' })
    }
    window.addEventListener(GLOBAL_LOADING_EVENT, handler)
    return () => window.removeEventListener(GLOBAL_LOADING_EVENT, handler)
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
        {globalLoading.active && <GlobalLoading message={globalLoading.message} />}
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
          <main className="main-content employee-main">
            <div className="page-header employee-topbar">
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
        {globalLoading.active && <GlobalLoading message={globalLoading.message} />}
      </BrowserRouter>
    )
  }

  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar onSettings={() => setSettingsOpen(true)} />
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
      {globalLoading.active && <GlobalLoading message={globalLoading.message} />}
      {settingsOpen && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setSettingsOpen(false) }}>
          <div className="modal-content settings-modal">
            <div className="settings-company">
              <div className="settings-company-logo">{currentUser.enterprise_name.charAt(0)}</div>
              <div>
                <div className="settings-label">当前企业</div>
                <h3>{currentUser.enterprise_name}</h3>
                <p>{currentUser.display_name || currentUser.username} · {currentUser.username}</p>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setSettingsOpen(false)}>关闭</button>
            </div>
            <div className="settings-actions">
              <button className="settings-action" onClick={openPasswordModal}>
                <span>修改密码</span>
                <small>更新当前管理员账号的登录密码</small>
              </button>
              <button className="settings-action danger" onClick={logout}>
                <span>退出登录</span>
                <small>退出当前企业管理后台</small>
              </button>
            </div>
          </div>
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
