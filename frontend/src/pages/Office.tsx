import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AgentAtDesk } from '../components/AgentDesk'
import { getAgents, type Agent } from '../api/client'

const STATUS_LABEL: Record<string, string> = {
  idle: '空闲',
  working: '工作中',
  blocked: '受阻',
  completed: '已完成',
}

export function Office({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')

  const load = useCallback(async (showError = true) => {
    try {
      setAgents(await getAgents())
    } catch {
      if (showError) showToast('加载 AI 办公室失败，请确认后端已启动', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    load()
    const timer = window.setInterval(() => load(false), 3000)
    return () => window.clearInterval(timer)
  }, [load])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return agents.filter(agent => {
      const matchesQuery = !q || [agent.name, agent.role, agent.department, agent.current_task || '']
        .join(' ')
        .toLowerCase()
        .includes(q)
      const matchesStatus = status === 'all' || agent.status === status
      return matchesQuery && matchesStatus
    })
  }, [agents, query, status])

  const counts = useMemo(() => ({
    all: agents.length,
    working: agents.filter(a => a.status === 'working').length,
    idle: agents.filter(a => a.status === 'idle').length,
    blocked: agents.filter(a => a.status === 'blocked').length,
  }), [agents])

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  return (
    <div>
      <div className="office-hero">
        <div>
          <h1 className="page-title">AI办公室</h1>
          <div className="office-subtitle">查看每个员工的实时状态、当前任务和工作入口。</div>
        </div>
        <Link to="/agents" className="btn btn-secondary">管理员工</Link>
      </div>

      <div className="office-toolbar">
        <input
          className="form-input office-search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="搜索员工、角色、部门或当前任务"
        />
        <div className="segmented">
          {[
            ['all', `全部 ${counts.all}`],
            ['working', `工作中 ${counts.working}`],
            ['idle', `空闲 ${counts.idle}`],
            ['blocked', `受阻 ${counts.blocked}`],
          ].map(([key, label]) => (
            <button
              key={key}
              className={status === key ? 'active' : ''}
              onClick={() => setStatus(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="office-board">
        <div className="office-grid office-grid-large">
          {filtered.map(agent => (
            <Link key={agent.id} to={`/agents/${agent.id}/chat`} className="office-desk-link">
              <AgentAtDesk agent={agent} />
              <div className="office-desk-meta">
                <div>
                  <div className="office-desk-name">{agent.name}</div>
                  <div className="office-desk-role">{agent.role}</div>
                </div>
                <span className={`status-badge status-${agent.status}`}>
                  <span className="status-dot" />
                  {STATUS_LABEL[agent.status] || agent.status}
                </span>
              </div>
            </Link>
          ))}
          {filtered.length === 0 && (
            <div className="empty-state">
              <div className="empty-text">没有匹配的 AI 员工。</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
