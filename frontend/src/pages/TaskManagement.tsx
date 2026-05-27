import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  deleteTask,
  getAgentTasks,
  getAgents,
  updateTask,
  type Agent,
  type TaskInfo,
} from '../api/client'

type TaskWithAgent = TaskInfo & { agent?: Agent }

const TASK_STATUS: Record<string, string> = {
  pending: '待处理',
  assigned: '已排队',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const REPEAT_LABEL: Record<string, string> = {
  none: '不重复',
  daily: '每天',
  weekly: '每周',
}

function displayTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function toDatetimeLocal(value: string | null | undefined) {
  const date = value ? new Date(value) : new Date(Date.now() + 10 * 60 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function TaskManagement({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [tasks, setTasks] = useState<TaskWithAgent[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [agentFilter, setAgentFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [editingTask, setEditingTask] = useState<TaskWithAgent | null>(null)
  const [form, setForm] = useState({
    title: '',
    description: '',
    task_type: 'immediate' as 'immediate' | 'scheduled',
    next_run_at: toDatetimeLocal(null),
    repeat: 'none' as 'none' | 'daily' | 'weekly',
    priority: 'normal',
    save_conversation: true,
  })

  const load = useCallback(async (showError = true) => {
    try {
      const agentData = await getAgents()
      const taskGroups = await Promise.all(agentData.map(async agent => {
        const agentTasks = await getAgentTasks(agent.id)
        return agentTasks.map(task => ({ ...task, agent }))
      }))
      setAgents(agentData)
      setTasks(taskGroups.flat().sort((a, b) => {
        const at = new Date(a.assigned_at || a.created_at || 0).getTime()
        const bt = new Date(b.assigned_at || b.created_at || 0).getTime()
        return bt - at
      }))
    } catch {
      if (showError) showToast('加载任务管理失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    load()
    const timer = window.setInterval(() => load(false), 5000)
    return () => window.clearInterval(timer)
  }, [load])

  const summary = useMemo(() => ({
    total: tasks.length,
    running: tasks.filter(t => t.status === 'running').length,
    scheduled: tasks.filter(t => t.task_type === 'scheduled').length,
    failed: tasks.filter(t => t.status === 'failed').length,
  }), [tasks])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return tasks.filter(task => {
      const matchesQuery = !q || [
        task.title,
        task.description,
        task.agent?.name || '',
        task.agent?.role || '',
      ].join(' ').toLowerCase().includes(q)
      const matchesAgent = agentFilter === 'all' || task.agent_id === agentFilter
      const matchesStatus = statusFilter === 'all' || task.status === statusFilter
      return matchesQuery && matchesAgent && matchesStatus
    })
  }, [agentFilter, query, statusFilter, tasks])

  const openEdit = (task: TaskWithAgent) => {
    setEditingTask(task)
    setForm({
      title: task.title,
      description: task.description || '',
      task_type: task.task_type === 'scheduled' ? 'scheduled' : 'immediate',
      next_run_at: toDatetimeLocal(task.next_run_at),
      repeat: (task.repeat as 'none' | 'daily' | 'weekly') || 'none',
      priority: task.priority || 'normal',
      save_conversation: task.save_conversation,
    })
  }

  const submitEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingTask || !form.title.trim()) return
    try {
      const nextRunAt = form.task_type === 'scheduled' ? new Date(form.next_run_at).toISOString() : null
      const updated = await updateTask(editingTask.id, {
        title: form.title.trim(),
        description: form.description.trim(),
        task_type: form.task_type,
        schedule: form.task_type === 'scheduled' ? `${displayTime(nextRunAt)} ${REPEAT_LABEL[form.repeat]}` : null,
        repeat: form.task_type === 'scheduled' ? form.repeat : 'none',
        priority: form.priority,
        save_conversation: form.save_conversation,
        next_run_at: nextRunAt,
      })
      setTasks(prev => prev.map(task => task.id === updated.id ? { ...updated, agent: task.agent } : task))
      setEditingTask(null)
      showToast('任务已更新', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : '更新任务失败', 'error')
    }
  }

  const removeTask = async (task: TaskWithAgent) => {
    if (!confirm(`确定删除任务「${task.title}」吗？`)) return
    try {
      await deleteTask(task.id)
      setTasks(prev => prev.filter(item => item.id !== task.id))
      showToast('任务已删除', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : '删除任务失败', 'error')
    }
  }

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">任务管理</h1>
          <div className="office-subtitle">统一查看、筛选和维护所有 AI 员工的任务记录。</div>
        </div>
      </div>

      <div className="management-hero">
        <div className="management-stat"><span>{summary.total}</span><b>全部任务</b></div>
        <div className="management-stat"><span>{summary.running}</span><b>执行中</b></div>
        <div className="management-stat"><span>{summary.scheduled}</span><b>定时任务</b></div>
        <div className="management-stat danger"><span>{summary.failed}</span><b>失败任务</b></div>
      </div>

      <div className="management-toolbar">
        <input className="form-input" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索任务、员工、角色" />
        <select className="form-select" value={agentFilter} onChange={e => setAgentFilter(e.target.value)}>
          <option value="all">全部员工</option>
          {agents.map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
        </select>
        <select className="form-select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="all">全部状态</option>
          {Object.entries(TASK_STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </div>

      <div className="task-management-table">
        {filtered.map(task => (
          <div key={task.id} className={`task-management-row task-${task.status}`}>
            <div className="task-main-cell">
              <div className="task-title">{task.title}</div>
              <div className="task-meta">{task.description || '无任务说明'}</div>
            </div>
            <div>
              <div className="agent-mini">
                <span className="name-tag-dot" style={{ background: task.agent?.avatar_color || '#64748b' }} />
                <div>
                  <strong>{task.agent?.name || task.agent_id}</strong>
                  <small>{task.agent?.role || '-'}</small>
                </div>
              </div>
            </div>
            <div><span className={`task-pill task-pill-${task.status}`}>{TASK_STATUS[task.status] || task.status}</span></div>
            <div className="task-meta">{task.task_type === 'scheduled' ? '定时' : '立即'} · {task.priority}</div>
            <div className="task-meta">下次：{displayTime(task.next_run_at)}</div>
            <div className="row-actions">
              <Link to={`/agents/${task.agent_id}/chat`} className="btn btn-ghost btn-sm">员工工作台</Link>
              <button className="btn btn-secondary btn-sm" onClick={() => openEdit(task)}>编辑</button>
              <button className="btn btn-ghost btn-sm danger-text" onClick={() => removeTask(task)} disabled={task.status === 'running'}>删除</button>
            </div>
          </div>
        ))}
        {filtered.length === 0 && <div className="empty-state"><div className="empty-text">没有匹配的任务。</div></div>}
      </div>

      {editingTask && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setEditingTask(null) }}>
          <div className="modal-content task-detail-modal">
            <div className="modal-header">
              <h3 className="modal-title">编辑任务</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditingTask(null)}>关闭</button>
            </div>
            <form className="task-form" onSubmit={submitEdit}>
              <label><span>任务标题</span><input className="form-input" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} required /></label>
              <label><span>任务说明</span><textarea className="form-textarea" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></label>
              <div className="form-grid">
                <label><span>任务类型</span><select className="form-select" value={form.task_type} onChange={e => setForm({ ...form, task_type: e.target.value as 'immediate' | 'scheduled' })}><option value="immediate">立即任务</option><option value="scheduled">定时任务</option></select></label>
                <label><span>优先级</span><select className="form-select" value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}><option value="low">低</option><option value="normal">普通</option><option value="high">高</option></select></label>
              </div>
              {form.task_type === 'scheduled' && (
                <div className="form-grid">
                  <label><span>下次执行</span><input className="form-input" type="datetime-local" value={form.next_run_at} onChange={e => setForm({ ...form, next_run_at: e.target.value })} required /></label>
                  <label><span>重复</span><select className="form-select" value={form.repeat} onChange={e => setForm({ ...form, repeat: e.target.value as 'none' | 'daily' | 'weekly' })}><option value="none">不重复</option><option value="daily">每天</option><option value="weekly">每周</option></select></label>
                </div>
              )}
              <label className="toggle-row"><input type="checkbox" checked={form.save_conversation} onChange={e => setForm({ ...form, save_conversation: e.target.checked })} />保存任务对话和执行过程</label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setEditingTask(null)}>取消</button>
                <button type="submit" className="btn btn-primary">保存修改</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
