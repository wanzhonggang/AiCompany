import { useCallback, useEffect, useMemo, useState } from 'react'
import { getOperationLogs, type OperationLog } from '../api/client'
import { formatBeijingTime } from '../utils/time'

const TARGET_LABEL: Record<string, string> = {
  agent: 'AI员工',
  department: '部门',
  task: '任务',
  admin: '管理员',
  model: '模型',
  model_provider: '模型厂商',
}

export function AuditLogs({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [logs, setLogs] = useState<OperationLog[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [targetType, setTargetType] = useState('all')

  const load = useCallback(async () => {
    try {
      setLogs(await getOperationLogs(300))
    } catch (e) {
      showToast(e instanceof Error ? e.message : '加载操作记录失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return logs.filter(log => {
      if (targetType !== 'all' && log.target_type !== targetType) return false
      if (!q) return true
      return [
        log.actor_username,
        log.actor_agent_name,
        log.action,
        log.target_name,
        log.detail,
      ].join(' ').toLowerCase().includes(q)
    })
  }, [logs, query, targetType])

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">操作记录</h1>
          <div className="office-subtitle">记录管理员对员工、部门、任务和模型的关键修改，以及 AI 员工新增任务的动作。</div>
        </div>
        <button className="btn btn-secondary" onClick={load}>刷新</button>
      </div>

      <div className="audit-toolbar">
        <input className="form-input" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索操作人、对象或说明" />
        <select className="form-select" value={targetType} onChange={e => setTargetType(e.target.value)}>
          <option value="all">全部对象</option>
          {Object.entries(TARGET_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>

      <div className="audit-table">
        <div className="audit-row audit-head">
          <span>时间</span>
          <span>操作人</span>
          <span>动作</span>
          <span>对象</span>
          <span>说明</span>
        </div>
        {filtered.map(log => (
          <div key={log.id} className="audit-row">
            <span>{formatBeijingTime(log.created_at)}</span>
            <span>
              <strong>{log.actor_agent_name || log.actor_username}</strong>
              <small>{log.actor_role === 'employee' ? 'AI员工' : '管理员'} · {log.actor_username}</small>
            </span>
            <span><span className="audit-action">{log.action}</span></span>
            <span>
              <strong>{log.target_name || log.target_id || '-'}</strong>
              <small>{TARGET_LABEL[log.target_type] || log.target_type}</small>
            </span>
            <span>{log.detail || '-'}</span>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <div className="empty-text">暂无匹配的操作记录</div>
          </div>
        )}
      </div>
    </div>
  )
}
