import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getStats, getAgents, type Stats, type Agent } from '../api/client'
import { AgentDeskRow } from '../components/AgentDesk'

const STATUS_ICONS: Record<string, { icon: string; cls: string }> = {
  total: { icon: '👥', cls: 'rgba(99,102,241,0.2)' },
  working: { icon: '⚡', cls: 'rgba(16,185,129,0.2)' },
  idle: { icon: '💤', cls: 'rgba(100,116,139,0.25)' },
  blocked: { icon: '🚫', cls: 'rgba(239,68,68,0.2)' },
  completed: { icon: '✅', cls: 'rgba(59,130,246,0.2)' },
}

export function Dashboard({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [s, a] = await Promise.all([getStats(), getAgents()])
      setStats(s)
      setAgents(a)
    } catch {
      showToast('加载数据失败，请确保后端已启动', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>

  const statItems = [
    { key: 'total', label: '总人数', value: stats?.total ?? 0 },
    { key: 'working', label: '工作中', value: stats?.working ?? 0 },
    { key: 'idle', label: '空闲中', value: stats?.idle ?? 0 },
    { key: 'blocked', label: '阻塞中', value: stats?.blocked ?? 0 },
    { key: 'completed', label: '已完成', value: stats?.completed ?? 0 },
  ]

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">控制台</h1>
      </div>

      <div className="stats-grid">
        {statItems.map(s => (
          <div key={s.key} className="stat-card">
            <div className="stat-icon" style={{ background: STATUS_ICONS[s.key]?.cls }}>
              {STATUS_ICONS[s.key]?.icon}
            </div>
            <div className="stat-info">
              <span className="stat-count">{s.value}</span>
              <span className="stat-label">{s.label}</span>
            </div>
          </div>
        ))}
      </div>

      <AgentDeskRow agents={agents} />

      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: 12 }}>AI 员工概览</h2>
        <div className="agent-grid">
          {agents.slice(0, 8).map(a => (
            <div key={a.id} className="agent-card">
              <div className="card-header">
                <div className="avatar" style={{ background: a.avatar_color }}>
                  {a.name.charAt(0)}
                </div>
                <span className={`status-badge status-${a.status}`}>
                  <span className="status-dot" />
                  {a.status === 'working' ? '工作中' : a.status === 'idle' ? '空闲中' : a.status === 'blocked' ? '阻塞中' : '已完成'}
                </span>
              </div>
              <div className="card-name">{a.name}</div>
              <div className="card-role">{a.role}</div>
              <div className="card-dept">{a.department || '—'}</div>
              <div className="card-current-task">
                <span className="task-label">当前任务：</span>
                {a.current_task ? <span className="task-value">{a.current_task}</span> : <span className="task-empty">无</span>}
              </div>
              <div className="skill-tags">
                {a.skills.slice(0, 4).map(s => <span key={s} className="skill-tag">{s}</span>)}
              </div>
              <div className="card-actions">
                <Link to={`/agents/${a.id}/chat`} className="btn btn-primary btn-sm">💬 对话</Link>
                <Link to="/agents" className="btn btn-ghost btn-sm">查看全部 →</Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
