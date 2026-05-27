import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createDepartment,
  deleteDepartment,
  getAgents,
  getDepartments,
  updateDepartment,
  type Agent,
  type Department,
} from '../api/client'

const COLORS = ['#f59e0b', '#10b981', '#06b6d4', '#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#14b8a6']

export function DepartmentManagement({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [departments, setDepartments] = useState<Department[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<Department | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', color: COLORS[0] })

  const load = useCallback(async (showError = true) => {
    try {
      const [deptData, agentData] = await Promise.all([getDepartments(), getAgents()])
      setDepartments(deptData)
      setAgents(agentData)
    } catch {
      if (showError) showToast('加载部门失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => { load() }, [load])

  const groupedAgents = useMemo(() => {
    const map = new Map<string, Agent[]>()
    for (const agent of agents) {
      const key = agent.department || '未分配'
      map.set(key, [...(map.get(key) || []), agent])
    }
    return map
  }, [agents])

  const filteredDepartments = useMemo(() => {
    const q = query.trim().toLowerCase()
    return departments.filter(dept => !q || [dept.name, dept.description].join(' ').toLowerCase().includes(q))
  }, [departments, query])

  const openCreate = () => {
    setEditing(null)
    setForm({ name: '', description: '', color: COLORS[Math.floor(Math.random() * COLORS.length)] })
    setShowForm(true)
  }

  const openEdit = (department: Department) => {
    setEditing(department)
    setForm({ name: department.name, description: department.description, color: department.color })
    setShowForm(true)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) return
    try {
      if (editing) {
        await updateDepartment(editing.id, form)
        showToast('部门已更新', 'success')
      } else {
        await createDepartment(form)
        showToast('部门已创建', 'success')
      }
      setShowForm(false)
      await load(false)
    } catch (err) {
      showToast(err instanceof Error ? err.message : '保存部门失败', 'error')
    }
  }

  const remove = async (department: Department) => {
    if (!confirm(`确定删除部门「${department.name}」吗？`)) return
    try {
      await deleteDepartment(department.id)
      await load(false)
      showToast('部门已删除', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : '删除部门失败', 'error')
    }
  }

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">部门管理</h1>
          <div className="office-subtitle">管理公司组织结构、部门职责和成员归属。</div>
        </div>
        <button className="btn btn-primary" onClick={openCreate}>新增部门</button>
      </div>

      <div className="management-toolbar" style={{ gridTemplateColumns: 'minmax(260px, 1fr) auto' }}>
        <input className="form-input" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索部门或职责" />
        <button className="btn btn-secondary" onClick={() => load(false)}>刷新</button>
      </div>

      <div className="department-grid">
        {filteredDepartments.map(dept => {
          const members = groupedAgents.get(dept.name) || []
          return (
            <div key={dept.id} className="department-card">
              <div className="department-accent" style={{ background: dept.color }} />
              <div className="department-card-header">
                <div>
                  <h2>{dept.name}</h2>
                  <p>{dept.description || '暂无职责说明'}</p>
                </div>
                <span className="model-badge ready">{members.length} 人</span>
              </div>
              <div className="department-members">
                {members.map(agent => (
                  <div key={agent.id} className="agent-mini">
                    <span className="name-tag-dot" style={{ background: agent.avatar_color }} />
                    <div><strong>{agent.name}</strong><small>{agent.role}</small></div>
                  </div>
                ))}
                {members.length === 0 && <div className="task-meta">暂无员工</div>}
              </div>
              <div className="row-actions">
                <button className="btn btn-secondary btn-sm" onClick={() => openEdit(dept)}>编辑</button>
                <button className="btn btn-ghost btn-sm danger-text" onClick={() => remove(dept)} disabled={members.length > 0}>删除</button>
              </div>
            </div>
          )
        })}
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowForm(false) }}>
          <div className="modal-content">
            <div className="modal-header">
              <h3 className="modal-title">{editing ? '编辑部门' : '新增部门'}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowForm(false)}>关闭</button>
            </div>
            <form className="task-form" onSubmit={submit}>
              <label><span>部门名称</span><input className="form-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required /></label>
              <label><span>部门职责</span><textarea className="form-textarea" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></label>
              <label>
                <span>部门颜色</span>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {COLORS.map(color => (
                    <button
                      key={color}
                      type="button"
                      className={`color-swatch ${form.color === color ? 'active' : ''}`}
                      style={{ background: color }}
                      onClick={() => setForm({ ...form, color })}
                    />
                  ))}
                </div>
              </label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>取消</button>
                <button type="submit" className="btn btn-primary">保存</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
