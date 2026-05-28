import { useCallback, useEffect, useState } from 'react'
import { beginGlobalLoading, createAdmin, getAdmins, type AdminAccount } from '../api/client'
import { formatBeijingTime } from '../utils/time'

export function AdminManagement({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [admins, setAdmins] = useState<AdminAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ username: '', display_name: '', password: '' })

  const load = useCallback(async () => {
    try {
      setAdmins(await getAdmins())
    } catch (e) {
      showToast(e instanceof Error ? e.message : '加载管理员失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => { load() }, [load])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.username.trim() || form.password.length < 6) {
      showToast('账号不能为空，密码至少 6 位', 'error')
      return
    }
    const stopLoading = beginGlobalLoading('正在创建管理员...')
    try {
      await createAdmin({
        username: form.username.trim(),
        password: form.password,
        display_name: form.display_name.trim() || '企业管理员',
      })
      setShowForm(false)
      setForm({ username: '', display_name: '', password: '' })
      await load()
      showToast('管理员已创建', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '创建管理员失败', 'error')
    } finally {
      stopLoading()
    }
  }

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">管理员管理</h1>
          <div className="office-subtitle">当前企业可以拥有多个管理员，共同维护部门、员工、任务和模型配置。</div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>新增管理员</button>
      </div>

      <div className="admin-grid">
        {admins.map(admin => (
          <div key={admin.id} className="admin-card">
            <div className="admin-avatar">{(admin.display_name || admin.username).charAt(0).toUpperCase()}</div>
            <div>
              <div className="admin-name">{admin.display_name || '企业管理员'}</div>
              <div className="task-meta">{admin.username}</div>
              <div className="task-meta">创建时间：{formatBeijingTime(admin.created_at)}</div>
            </div>
            <span className={`model-badge ${admin.enabled ? 'ready' : ''}`}>{admin.enabled ? '已启用' : '已停用'}</span>
          </div>
        ))}
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowForm(false) }}>
          <div className="modal-content" style={{ maxWidth: 460 }}>
            <div className="modal-header">
              <h3 className="modal-title">新增管理员</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowForm(false)}>关闭</button>
            </div>
            <form onSubmit={submit} className="task-form">
              <label>
                <span>管理员账号</span>
                <input className="form-input" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} placeholder="例如 admin2" />
              </label>
              <label>
                <span>显示名称</span>
                <input className="form-input" value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} placeholder="例如 财务管理员" />
              </label>
              <label>
                <span>初始密码</span>
                <input className="form-input" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} placeholder="至少 6 位" />
              </label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>取消</button>
                <button type="submit" className="btn btn-primary">创建管理员</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
