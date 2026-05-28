import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getAgents, deleteAgent, createAgent, updateAgent, updateEmployeePassword, getLLMConfig, getDepartments, type Agent, type Department, type LLMConfig } from '../api/client'

const AVATAR_COLORS = [
  "#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b",
  "#f97316","#ef4444","#ec4899","#14b8a6","#84cc16"
]

const STATUS_MAP: Record<string, string> = {
  idle: '空闲中', working: '工作中', blocked: '阻塞中', completed: '已完成',
}

export function Agents({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Agent | null>(null)
  const [passwordAgent, setPasswordAgent] = useState<Agent | null>(null)
  const [employeePassword, setEmployeePassword] = useState('')
  const [passwordMode, setPasswordMode] = useState<'initial' | 'edit'>('edit')
  const [searchQuery, setSearchQuery] = useState('')
  const [filterStatus, setFilterStatus] = useState('all')

  // Form state
  const [formName, setFormName] = useState('')
  const [formRole, setFormRole] = useState('')
  const [formDept, setFormDept] = useState('')
  const [formSkills, setFormSkills] = useState('')
  const [formPrompt, setFormPrompt] = useState('')
  const [formColor, setFormColor] = useState(AVATAR_COLORS[0])
  const [formProvider, setFormProvider] = useState('')
  const [formModel, setFormModel] = useState('')
  const [llmConfig, setLLMConfig] = useState<LLMConfig | null>(null)
  const [departments, setDepartments] = useState<Department[]>([])

  const availableProviders = (llmConfig?.providers || []).filter(p => p.configured && p.status === 'ready')
  const currentProvider = availableProviders.find(p => p.name === formProvider)
  const firstAvailableProvider = availableProviders[0]
  const defaultProviderAvailable = availableProviders.find(p => p.name === llmConfig?.default_provider)

  const loadLLMConfig = useCallback(async () => {
    try {
      const cfg = await getLLMConfig()
      setLLMConfig(cfg)
      const usableDefault = cfg.providers.find(p => p.name === cfg.default_provider && p.configured && p.status === 'ready')
      const fallback = usableDefault || cfg.providers.find(p => p.configured && p.status === 'ready')
      setFormProvider(fallback?.name || '')
      setFormModel(fallback?.models[0]?.name || '')
    } catch { /* no-op, wait for backend */ }
  }, [])

  const load = useCallback(async (showError = true) => {
    try {
      const [agentData, departmentData] = await Promise.all([getAgents(), getDepartments()])
      setAgents(agentData)
      setDepartments(departmentData)
    } catch {
      if (showError) showToast('加载失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    load()
    loadLLMConfig()
    const timer = window.setInterval(() => load(false), 3000)
    return () => window.clearInterval(timer)
  }, [load, loadLLMConfig])

  const openCreate = () => {
    setEditing(null)
    setFormName(''); setFormRole(''); setFormDept('')
    setFormSkills(''); setFormPrompt('')
    const provider = defaultProviderAvailable || firstAvailableProvider
    setFormProvider(provider?.name || '')
    setFormModel(provider?.models[0]?.name || '')
    setFormColor(AVATAR_COLORS[Math.floor(Math.random() * AVATAR_COLORS.length)])
    setShowForm(true)
  }

  const openEdit = (a: Agent) => {
    setEditing(a)
    setFormName(a.name); setFormRole(a.role); setFormDept(a.department)
    setFormSkills(a.skills.join(', ')); setFormPrompt(a.system_prompt)
    setFormColor(a.avatar_color)
    const agentProvider = availableProviders.find(p => p.name === a.provider)
    const provider = agentProvider || defaultProviderAvailable || firstAvailableProvider
    const model = provider?.models.find(m => m.name === a.model_name) || provider?.models[0]
    setFormProvider(provider?.name || '')
    setFormModel(model?.name || '')
    setShowForm(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim() || !formRole.trim()) return
    if (!formProvider || !formModel) {
      showToast('未选择模型，不可新增AI员工', 'error')
      return
    }

    try {
      if (editing) {
        await updateAgent(editing.id, {
          name: formName, role: formRole, department: formDept,
          skills: formSkills.split(',').map(s => s.trim()).filter(Boolean),
          system_prompt: formPrompt, avatar_color: formColor,
          provider: formProvider, model_name: formModel,
        } as Partial<Agent>)
        showToast('员工信息已更新', 'success')
      } else {
        const created = await createAgent({
          name: formName, role: formRole, department: formDept,
          skills: formSkills.split(',').map(s => s.trim()).filter(Boolean),
          system_prompt: formPrompt, avatar_color: formColor,
          provider: formProvider, model_name: formModel,
        } as Partial<Agent>)
        setPasswordAgent(created)
        setPasswordMode('initial')
        setEmployeePassword('')
        showToast('AI 员工已添加，请设置员工登录密码', 'success')
      }
      setShowForm(false)
      load()
    } catch (e) {
      showToast(e instanceof Error ? e.message : '操作失败', 'error')
    }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定删除「${name}」吗？此操作不可撤销。`)) return
    try {
      await deleteAgent(id)
      showToast(`已删除「${name}」`, 'info')
      load()
    } catch {
      showToast('删除失败', 'error')
    }
  }

  const submitEmployeePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!passwordAgent || employeePassword.length < 6) {
      showToast('密码至少 6 位', 'error')
      return
    }
    try {
      await updateEmployeePassword(passwordAgent.id, employeePassword)
      showToast(passwordMode === 'initial' ? '员工密码已设置，可以登录了' : '员工密码已更新', 'success')
      setPasswordAgent(null)
      setEmployeePassword('')
      setPasswordMode('edit')
      load(false)
    } catch (e) {
      showToast(e instanceof Error ? e.message : '修改员工密码失败', 'error')
    }
  }

  const filtered = agents.filter(a => {
    if (filterStatus !== 'all' && a.status !== filterStatus) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      if (!a.name.toLowerCase().includes(q) && !a.role.toLowerCase().includes(q)) return false
    }
    return true
  })

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">🤖 AI 员工</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            type="text" className="form-input" placeholder="搜索姓名或职位..."
            style={{ width: 200 }} value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
          <select className="form-select" style={{ width: 120 }} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
            <option value="all">全部状态</option>
            <option value="working">工作中</option>
            <option value="idle">空闲中</option>
            <option value="blocked">阻塞中</option>
            <option value="completed">已完成</option>
          </select>
          <button className="btn btn-primary" onClick={openCreate}>+ 添加员工</button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">{searchQuery ? '🔍' : '🤖'}</div>
          <div className="empty-text">
            {searchQuery ? '没有找到匹配的员工' : '还没有 AI 员工，点击上方按钮添加'}
          </div>
        </div>
      ) : (
        <div className="agent-grid">
          {filtered.map(a => (
            <div key={a.id} className="agent-card">
              <div className="card-header">
                <div className="avatar" style={{ background: a.avatar_color }}>{a.name.charAt(0)}</div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => openEdit(a)}>✎</button>
                  <button className="btn btn-ghost btn-sm" style={{ color: 'var(--color-blocked)' }} onClick={() => handleDelete(a.id, a.name)}>🗑</button>
                </div>
              </div>
              <div className="card-name">{a.name}</div>
              <div className="card-role">{a.role}</div>
              <div className="card-dept">{a.department || '—'}</div>
              <div className="card-dept">账号：{a.employee_username || '未生成'}</div>
              <span className={`status-badge status-${a.status}`}>
                <span className="status-dot" />{STATUS_MAP[a.status] || a.status}
              </span>
              <div className="card-current-task">
                <span className="task-label">当前任务：</span>
                {a.current_task ? <span className="task-value">{a.current_task}</span> : <span className="task-empty">无</span>}
              </div>
              <div className="skill-tags">
                {a.skills.map(s => <span key={s} className="skill-tag">{s}</span>)}
              </div>
              <div className="card-actions">
                <Link to={`/agents/${a.id}/chat`} className="btn btn-primary btn-sm">进入工作台</Link>
                <button className="btn btn-secondary btn-sm" onClick={() => {
                  setPasswordAgent(a)
                  setPasswordMode('edit')
                  setEmployeePassword('')
                }}>改密码</button>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', alignSelf: 'center' }}>
                  {a.tool_count} 个工具
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {showForm && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowForm(false) }}>
          <div className="modal-content">
            <div className="modal-header">
              <h3 className="modal-title">{editing ? '编辑 AI 员工' : '添加 AI 员工'}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowForm(false)}>✕</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 4 }}>姓名 *</label>
                  <input className="form-input" value={formName} onChange={e => setFormName(e.target.value)} placeholder="例如：智能助手 Alpha" maxLength={50} required />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 4 }}>职位 *</label>
                  <input className="form-input" value={formRole} onChange={e => setFormRole(e.target.value)} placeholder="例如：高级前端工程师" maxLength={50} required />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 4 }}>部门</label>
                  <select className="form-select" value={formDept} onChange={e => setFormDept(e.target.value)} required>
                    <option value="">请选择部门</option>
                    {departments.map(dept => <option key={dept.id} value={dept.name}>{dept.name}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 4 }}>技能（逗号分隔）</label>
                  <input className="form-input" value={formSkills} onChange={e => setFormSkills(e.target.value)} placeholder="React, TypeScript, Node.js" />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 4 }}>系统提示词</label>
                  <textarea className="form-textarea" value={formPrompt} onChange={e => setFormPrompt(e.target.value)} placeholder="定义这个AI员工的行为方式..." />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 4 }}>LLM 供应商</label>
                    <select className="form-select" value={formProvider} disabled={availableProviders.length === 0} onChange={e => {
                      setFormProvider(e.target.value)
                      const provider = availableProviders.find(p => p.name === e.target.value)
                      setFormModel(provider?.models[0]?.name || '')
                    }}>
                      {availableProviders.length === 0 && <option value="">请先配置 API Key</option>}
                      {availableProviders.map(p => (
                        <option key={p.name} value={p.name}>{p.display_name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 4 }}>模型</label>
                    <select className="form-select" value={formModel} disabled={!currentProvider} onChange={e => setFormModel(e.target.value)}>
                      {!currentProvider && <option value="">暂无可用模型</option>}
                      {(currentProvider?.models || []).map(m => (
                        <option key={m.name} value={m.name}>{m.display_name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                {availableProviders.length === 0 && (
                  <div className="form-help-error">
                    当前企业未配置可用模型。请先进入「模型管理」填写并通过 API Key 校验后再创建 AI 员工。
                  </div>
                )}
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 4 }}>头像颜色</label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {AVATAR_COLORS.map(c => (
                      <div key={c} onClick={() => setFormColor(c)} style={{
                        width: 32, height: 32, borderRadius: '50%', background: c, cursor: 'pointer',
                        border: formColor === c ? '2px solid #fff' : '2px solid transparent',
                        boxShadow: formColor === c ? '0 0 0 2px var(--accent)' : 'none',
                      }} />
                    ))}
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
                  {availableProviders.length > 0 && <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>取消</button>}
                  <button type="submit" className="btn btn-primary">{editing ? '保存修改' : '确认添加'}</button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {passwordAgent && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setPasswordAgent(null) }}>
          <div className="modal-content" style={{ maxWidth: 420 }}>
            <div className="modal-header">
              <h3 className="modal-title">{passwordMode === 'initial' ? '设置员工登录密码' : '修改员工密码'}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setPasswordAgent(null)}>关闭</button>
            </div>
            <form onSubmit={submitEmployeePassword} className="task-form">
              <div className="task-meta">账号不可修改：{passwordAgent.employee_username || '未生成'}</div>
              {passwordMode === 'initial' && (
                <div className="form-help-error" style={{ borderColor: 'rgba(6,182,212,0.25)', background: 'rgba(6,182,212,0.08)', color: 'var(--text-secondary)' }}>
                  请在这里设置员工初始密码。设置完成后，员工就可以用上面的账号和这个密码从“员工登录”入口进入。
                </div>
              )}
              <label>
                <span>新密码</span>
                <input
                  className="form-input"
                  type="password"
                  value={employeePassword}
                  onChange={e => setEmployeePassword(e.target.value)}
                  placeholder="至少 6 位"
                  autoFocus
                />
              </label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setPasswordAgent(null)}>取消</button>
                <button type="submit" className="btn btn-primary">{passwordMode === 'initial' ? '设置并启用' : '保存密码'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
