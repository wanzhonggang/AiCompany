import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CompactAgentDesk } from '../components/AgentDesk'
import { getAgents, getDepartments, type Agent, type Department } from '../api/client'

const STATUS_LABEL: Record<string, string> = {
  idle: '空闲',
  working: '工作中',
  blocked: '受阻',
  completed: '已完成',
}

export function Office({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')

  const load = useCallback(async (showError = true) => {
    try {
      const [agentData, departmentData] = await Promise.all([getAgents(), getDepartments()])
      setAgents(agentData)
      setDepartments(departmentData)
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

  const groupedByDepartment = useMemo(() => {
    const groups = departments.map(dept => ({
      department: dept,
      agents: filtered.filter(agent => (agent.department || '未分配') === dept.name),
    }))
    const knownNames = new Set(departments.map(dept => dept.name))
    const ungrouped = filtered.filter(agent => !knownNames.has(agent.department || '未分配'))
    if (ungrouped.length > 0) {
      groups.push({
        department: {
          id: 'ungrouped',
          name: '未分配',
          description: '尚未归属到正式部门的 AI 员工。',
          color: '#64748b',
          member_count: ungrouped.length,
          created_at: null,
          updated_at: null,
        },
        agents: ungrouped,
      })
    }
    return groups.filter(group => group.agents.length > 0 || !query.trim())
  }, [departments, filtered, query])

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

      <div className="office-overview-grid">
        {groupedByDepartment.map(group => (
          <section key={group.department.id} className="office-department-frame">
            <div className="office-department-header">
              <div>
                <h2><span style={{ background: group.department.color }} />{group.department.name}</h2>
                <p>{group.department.description || '暂无部门职责说明'}</p>
              </div>
              <strong>{group.agents.length} 人</strong>
            </div>
            <div className="department-mini-strip">
                {group.agents.map(agent => (
                  <Link key={agent.id} to={`/agents/${agent.id}/chat`} className="mini-agent-card">
                    <CompactAgentDesk agent={agent} />
                    <div className="mini-agent-name">{agent.name}</div>
                    <div className="mini-agent-role">{agent.role}</div>
                    <div className={`mini-agent-status status-${agent.status}`}>
                      <span className="status-dot" />
                      {STATUS_LABEL[agent.status] || agent.status}
                    </div>
                  </Link>
                ))}
                {group.agents.length === 0 && <div className="empty-mini">该部门暂无匹配员工。</div>}
            </div>
          </section>
        ))}
        {filtered.length === 0 && (
          <div className="empty-state">
            <div className="empty-text">没有匹配的 AI 员工。</div>
          </div>
        )}
      </div>
    </div>
  )
}
