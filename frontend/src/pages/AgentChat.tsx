import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  chatWithAgent,
  createTask,
  deleteConversation,
  deleteTask,
  getAgent,
  getAgentTasks,
  getConversations,
  getMessages,
  renameConversation,
  updateTask,
  type Agent,
  type ChatMessageHistory,
  type Conversation,
  type TaskInfo,
} from '../api/client'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'error' | 'thinking'
  content: string
  data?: Record<string, unknown>
  toolCalls?: Array<{ id: string; name: string; input: Record<string, unknown> }>
}

type TaskFormState = {
  title: string
  description: string
  task_type: 'immediate' | 'scheduled'
  next_run_at: string
  repeat: 'none' | 'daily' | 'weekly'
  priority: string
  save_conversation: boolean
}

const STATUS_MAP: Record<string, string> = {
  idle: '空闲中',
  working: '工作中',
  blocked: '受阻中',
  completed: '已完成',
}

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

function toDatetimeLocal(value: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`
}

function toDatetimeLocalFromIso(value: string | null | undefined) {
  if (!value) return toDatetimeLocal(new Date(Date.now() + 10 * 60 * 1000))
  return toDatetimeLocal(new Date(value))
}

function displayTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

export function AgentChat({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const { id } = useParams<{ id: string }>()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [convs, setConvs] = useState<Conversation[]>([])
  const [tasks, setTasks] = useState<TaskInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [saveConversation, setSaveConversation] = useState(true)
  const [editingTitle, setEditingTitle] = useState<string | null>(null)
  const [titleInput, setTitleInput] = useState('')
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [selectedTask, setSelectedTask] = useState<TaskInfo | null>(null)
  const [taskForm, setTaskForm] = useState<TaskFormState>({
    title: '',
    description: '',
    task_type: 'immediate' as 'immediate' | 'scheduled',
    next_run_at: toDatetimeLocal(new Date(Date.now() + 10 * 60 * 1000)),
    repeat: 'none' as 'none' | 'daily' | 'weekly',
    priority: 'normal',
    save_conversation: true,
  })
  const [taskEditForm, setTaskEditForm] = useState<TaskFormState>({
    title: '',
    description: '',
    task_type: 'immediate',
    next_run_at: toDatetimeLocal(new Date(Date.now() + 10 * 60 * 1000)),
    repeat: 'none',
    priority: 'normal',
    save_conversation: true,
  })
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const loadMessages = useCallback(async (convId: string) => {
    try {
      const history = await getMessages(convId)
      const msgs: ChatMessage[] = history.map((m: ChatMessageHistory) => ({
        id: m.id,
        role: m.role as ChatMessage['role'],
        content: m.content,
        toolCalls: m.tool_calls || undefined,
      }))
      setMessages(msgs)
    } catch {
      showToast('加载对话记录失败', 'error')
    }
  }, [showToast])

  const loadWorkspace = useCallback(async (showError = true) => {
    if (!id) return
    try {
      const [agentData, convData, taskData] = await Promise.all([
        getAgent(id),
        getConversations(id),
        getAgentTasks(id),
      ])
      setAgent(agentData)
      setConvs(convData)
      setTasks(taskData)
      if (!conversationId && convData.length > 0) {
        setConversationId(convData[0].id)
        await loadMessages(convData[0].id)
      }
    } catch {
      if (showError) showToast('加载员工工作台失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [conversationId, id, loadMessages, showToast])

  useEffect(() => {
    loadWorkspace()
    const timer = window.setInterval(() => loadWorkspace(false), 3000)
    return () => window.clearInterval(timer)
  }, [loadWorkspace])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const selectedConversation = useMemo(
    () => convs.find(c => c.id === conversationId) || null,
    [convs, conversationId],
  )

  const openTaskDetail = (task: TaskInfo) => {
    setSelectedTask(task)
    setTaskEditForm({
      title: task.title,
      description: task.description || '',
      task_type: task.task_type === 'scheduled' ? 'scheduled' : 'immediate',
      next_run_at: toDatetimeLocalFromIso(task.next_run_at),
      repeat: (task.repeat as 'none' | 'daily' | 'weekly') || 'none',
      priority: task.priority || 'normal',
      save_conversation: task.save_conversation,
    })
  }

  const handleDeleteConversation = async () => {
    if (!selectedConversation || sending) return
    if (!confirm(`确定删除对话「${selectedConversation.title}」吗？删除后无法恢复。`)) return

    try {
      await deleteConversation(selectedConversation.id)
      const nextConvs = convs.filter(c => c.id !== selectedConversation.id)
      setConvs(nextConvs)

      const nextConv = nextConvs[0] || null
      if (nextConv) {
        setConversationId(nextConv.id)
        await loadMessages(nextConv.id)
      } else {
        setConversationId(null)
        setMessages([])
      }

      if (id) {
        getAgentTasks(id).then(setTasks).catch(() => {})
      }
      showToast('对话已删除', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '删除对话失败', 'error')
    }
  }

  const handleSend = () => {
    if (!input.trim() || sending || !id) return
    const originalAgent = agent
    const content = input.trim()
    const transientConversation = !saveConversation

    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setSending(true)
    if (agent) setAgent({ ...agent, status: 'working', current_task: content.slice(0, 200) })

    const assistantId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '' }])

    abortRef.current = chatWithAgent(
      id,
      content,
      saveConversation ? conversationId : null,
      saveConversation,
      (eventType, data) => {
        switch (eventType) {
          case 'thinking':
          case 'tool_use':
          case 'tool_result':
            setMessages(prev => [...prev, {
              id: `${Date.now()}-${prev.length}`,
              role: 'tool',
              content: data.content,
              data: data.data,
            }])
            break
          case 'text_delta':
            setMessages(prev => prev.map(m =>
              m.id === assistantId ? { ...m, content: m.content + data.content } : m
            ))
            break
          case 'done': {
            setAgent(prev => prev ? { ...prev, status: 'idle', current_task: null } : prev)
            const { conversation_id } = data.data as Record<string, unknown>
            if (saveConversation && conversation_id && !conversationId) {
              setConversationId(conversation_id as string)
            }
            if (saveConversation) {
              getConversations(id).then(setConvs).catch(() => {})
            }
            setMessages(prev => prev.map(m =>
              m.id === assistantId && !m.content ? { ...m, content: '(任务已完成)' } : m
            ))
            break
          }
          case 'error':
            setAgent(prev => prev ? { ...prev, status: 'blocked', current_task: null } : prev)
            setMessages(prev => [...prev, { id: `${Date.now()}-error`, role: 'error', content: data.content }])
            break
        }
      },
      () => {
        setSending(false)
        if (id) {
          Promise.all([getAgent(id), getAgentTasks(id)])
            .then(([freshAgent, freshTasks]) => {
              setAgent(freshAgent)
              setTasks(freshTasks)
            })
            .catch(() => {
              setAgent(prev => prev ? { ...prev, status: originalAgent?.status || 'idle', current_task: null } : prev)
            })
        }
        if (transientConversation) {
          showToast('本次对话未保存', 'success')
        }
      },
      (err) => {
        setMessages(prev => [...prev, { id: `${Date.now()}-conn`, role: 'error', content: `连接错误: ${err}` }])
        setAgent(prev => prev ? { ...prev, status: 'blocked', current_task: null } : prev)
        setSending(false)
      },
    )
  }

  const handleStop = () => {
    abortRef.current?.abort()
    setSending(false)
    setAgent(prev => prev ? { ...prev, status: 'idle', current_task: null } : prev)
  }

  const submitTask = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!id || !taskForm.title.trim()) return
    try {
      const nextRunAt = taskForm.task_type === 'scheduled'
        ? new Date(taskForm.next_run_at).toISOString()
        : null
      await createTask(id, {
        title: taskForm.title.trim(),
        description: taskForm.description.trim(),
        task_type: taskForm.task_type,
        schedule: taskForm.task_type === 'scheduled' ? `${displayTime(nextRunAt)} ${REPEAT_LABEL[taskForm.repeat]}` : null,
        repeat: taskForm.task_type === 'scheduled' ? taskForm.repeat : 'none',
        priority: taskForm.priority,
        save_conversation: taskForm.save_conversation,
        next_run_at: nextRunAt,
      })
      showToast(taskForm.task_type === 'scheduled' ? '定时任务已创建' : '任务已创建并开始执行', 'success')
      setTaskModalOpen(false)
      setTaskForm(prev => ({ ...prev, title: '', description: '' }))
      await loadWorkspace(false)
    } catch (e) {
      showToast(e instanceof Error ? e.message : '创建任务失败', 'error')
    }
  }

  const submitTaskEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTask || !taskEditForm.title.trim()) return
    try {
      const nextRunAt = taskEditForm.task_type === 'scheduled'
        ? new Date(taskEditForm.next_run_at).toISOString()
        : null
      const updated = await updateTask(selectedTask.id, {
        title: taskEditForm.title.trim(),
        description: taskEditForm.description.trim(),
        task_type: taskEditForm.task_type,
        schedule: taskEditForm.task_type === 'scheduled' ? `${displayTime(nextRunAt)} ${REPEAT_LABEL[taskEditForm.repeat]}` : null,
        repeat: taskEditForm.task_type === 'scheduled' ? taskEditForm.repeat : 'none',
        priority: taskEditForm.priority,
        save_conversation: taskEditForm.save_conversation,
        next_run_at: nextRunAt,
      })
      setTasks(prev => prev.map(task => task.id === updated.id ? updated : task))
      setSelectedTask(updated)
      showToast('任务已更新', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '更新任务失败', 'error')
    }
  }

  const handleDeleteTask = async () => {
    if (!selectedTask) return
    if (!confirm(`确定删除任务「${selectedTask.title}」吗？任务记录删除后无法恢复。`)) return
    try {
      await deleteTask(selectedTask.id)
      setTasks(prev => prev.filter(task => task.id !== selectedTask.id))
      setSelectedTask(null)
      showToast('任务已删除', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '删除任务失败', 'error')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>
  if (!agent) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>未找到 AI 员工</div>

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link to="/office" className="btn btn-ghost btn-sm">← 返回办公室</Link>
          <div className="avatar" style={{ background: agent.avatar_color, width: 40, height: 40, fontSize: '0.95rem' }}>
            {agent.name.charAt(0)}
          </div>
          <div>
            <h1 className="page-title" style={{ fontSize: '1.2rem', margin: 0 }}>{agent.name} 工作台</h1>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              {agent.role} · <span className={`status-badge status-${agent.status}`} style={{ fontSize: '0.72rem' }}>
                <span className="status-dot" />{STATUS_MAP[agent.status] || agent.status}
              </span>
            </span>
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setTaskModalOpen(true)}>新建任务</button>
      </div>

      <div className="workspace-layout">
        <aside className="task-panel">
          <div className="panel-title">任务记录</div>
          <div className="task-list">
            {tasks.map(task => (
              <div
                key={task.id}
                className={`task-item task-${task.status}`}
                role="button"
                tabIndex={0}
                onClick={() => openTaskDetail(task)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    openTaskDetail(task)
                  }
                }}
              >
                <div className="task-row">
                  <div className="task-title">{task.title}</div>
                  <span className={`task-pill task-pill-${task.status}`}>{TASK_STATUS[task.status] || task.status}</span>
                </div>
                <div className="task-meta">
                  {task.task_type === 'scheduled' ? '定时任务' : '立即任务'} · {task.priority}
                </div>
                {task.next_run_at && <div className="task-meta">下次执行：{displayTime(task.next_run_at)}</div>}
                {task.last_run_at && <div className="task-meta">上次执行：{displayTime(task.last_run_at)}</div>}
                {task.output && <div className="task-output">{task.output}</div>}
                {task.error && <div className="task-error">{task.error}</div>}
                <div className="task-actions">
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={e => {
                      e.stopPropagation()
                      openTaskDetail(task)
                    }}
                  >
                    详情
                  </button>
                  {task.conversation_id && (
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={e => {
                      e.stopPropagation()
                      setConversationId(task.conversation_id)
                      loadMessages(task.conversation_id!)
                    }}
                  >
                    查看对话
                  </button>
                  )}
                </div>
              </div>
            ))}
            {tasks.length === 0 && <div className="empty-mini">还没有任务，点击右上角新建。</div>}
          </div>
        </aside>

        <section className="chat-panel">
          <div className="chat-toolbar">
            <select
              className="form-select"
              value={conversationId || ''}
              onChange={async e => {
                const cid = e.target.value || null
                setConversationId(cid)
                if (cid) await loadMessages(cid)
                else setMessages([])
              }}
            >
              <option value="">新临时对话</option>
              {convs.map(c => (
                <option key={c.id} value={c.id}>{c.title} · {new Date(c.updated_at || c.created_at).toLocaleDateString('zh-CN')}</option>
              ))}
            </select>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setConversationId(null)
                setMessages([])
              }}
            >
              新对话
            </button>
            {selectedConversation && (
              <>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setEditingTitle(selectedConversation.id)
                    setTitleInput(selectedConversation.title)
                  }}
                >
                  重命名
                </button>
                <button
                  className="btn btn-ghost btn-sm danger-text"
                  onClick={handleDeleteConversation}
                  disabled={sending}
                >
                  删除
                </button>
              </>
            )}
          </div>

          <div className="chat-layout workspace-chat">
            <div className="chat-messages">
              {messages.length === 0 && (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                  向 {agent.name} 发送消息，或从左侧任务记录打开历史对话。
                </div>
              )}
              {messages.map(m => (
                <div key={m.id} className={`chat-msg ${m.role}`}>
                  {m.content}
                </div>
              ))}
              {sending && <div className="typing-indicator">AI 正在处理...</div>}
              <div ref={messagesEndRef} />
            </div>

            <div className="save-row">
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={saveConversation}
                  onChange={e => setSaveConversation(e.target.checked)}
                />
                保存本次对话
              </label>
              {!saveConversation && <span className="hint-text">关闭后只在当前页面显示，不写入历史。</span>}
            </div>

            <div className="chat-input-area">
              <textarea
                className="chat-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`给 ${agent.name} 安排工作或进行简单对话`}
                rows={2}
                disabled={sending}
              />
              {sending ? (
                <button className="btn btn-danger" onClick={handleStop}>停止</button>
              ) : (
                <button className="btn btn-primary" onClick={handleSend} disabled={!input.trim()}>
                  发送
                </button>
              )}
            </div>
          </div>
        </section>
      </div>

      {editingTitle && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setEditingTitle(null) }}>
          <div className="modal-content" style={{ maxWidth: 380 }}>
            <div className="modal-header">
              <h3 className="modal-title">重命名对话</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditingTitle(null)}>关闭</button>
            </div>
            <form onSubmit={async e => {
              e.preventDefault()
              if (titleInput.trim() && editingTitle) {
                await renameConversation(editingTitle, titleInput.trim())
                setConvs(prev => prev.map(c => c.id === editingTitle ? { ...c, title: titleInput.trim() } : c))
                setEditingTitle(null)
              }
            }}>
              <input className="form-input" value={titleInput} onChange={e => setTitleInput(e.target.value)} placeholder="对话名称" autoFocus />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
                <button type="button" className="btn btn-secondary" onClick={() => setEditingTitle(null)}>取消</button>
                <button type="submit" className="btn btn-primary">保存</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {selectedTask && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setSelectedTask(null) }}>
          <div className="modal-content task-detail-modal">
            <div className="modal-header">
              <div>
                <h3 className="modal-title">任务详情</h3>
                <div className="task-meta">
                  {TASK_STATUS[selectedTask.status] || selectedTask.status} · 创建于 {displayTime(selectedTask.created_at)}
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelectedTask(null)}>关闭</button>
            </div>
            <form onSubmit={submitTaskEdit} className="task-form">
              <label>
                <span>任务标题</span>
                <input
                  className="form-input"
                  value={taskEditForm.title}
                  onChange={e => setTaskEditForm({ ...taskEditForm, title: e.target.value })}
                  disabled={selectedTask.status === 'running'}
                  required
                />
              </label>
              <label>
                <span>任务说明</span>
                <textarea
                  className="form-textarea"
                  value={taskEditForm.description}
                  onChange={e => setTaskEditForm({ ...taskEditForm, description: e.target.value })}
                  disabled={selectedTask.status === 'running'}
                />
              </label>
              <div className="form-grid">
                <label>
                  <span>任务类型</span>
                  <select
                    className="form-select"
                    value={taskEditForm.task_type}
                    onChange={e => setTaskEditForm({ ...taskEditForm, task_type: e.target.value as 'immediate' | 'scheduled' })}
                    disabled={selectedTask.status === 'running'}
                  >
                    <option value="immediate">立即任务</option>
                    <option value="scheduled">定时任务</option>
                  </select>
                </label>
                <label>
                  <span>优先级</span>
                  <select
                    className="form-select"
                    value={taskEditForm.priority}
                    onChange={e => setTaskEditForm({ ...taskEditForm, priority: e.target.value })}
                    disabled={selectedTask.status === 'running'}
                  >
                    <option value="low">低</option>
                    <option value="normal">普通</option>
                    <option value="high">高</option>
                  </select>
                </label>
              </div>
              {taskEditForm.task_type === 'scheduled' && (
                <div className="form-grid">
                  <label>
                    <span>下次执行时间</span>
                    <input
                      className="form-input"
                      type="datetime-local"
                      value={taskEditForm.next_run_at}
                      onChange={e => setTaskEditForm({ ...taskEditForm, next_run_at: e.target.value })}
                      disabled={selectedTask.status === 'running'}
                      required
                    />
                  </label>
                  <label>
                    <span>重复</span>
                    <select
                      className="form-select"
                      value={taskEditForm.repeat}
                      onChange={e => setTaskEditForm({ ...taskEditForm, repeat: e.target.value as 'none' | 'daily' | 'weekly' })}
                      disabled={selectedTask.status === 'running'}
                    >
                      <option value="none">不重复</option>
                      <option value="daily">每天</option>
                      <option value="weekly">每周</option>
                    </select>
                  </label>
                </div>
              )}
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={taskEditForm.save_conversation}
                  onChange={e => setTaskEditForm({ ...taskEditForm, save_conversation: e.target.checked })}
                  disabled={selectedTask.status === 'running'}
                />
                保存任务对话和执行过程
              </label>

              <div className="task-detail-grid">
                <div><span>上次执行</span><strong>{displayTime(selectedTask.last_run_at)}</strong></div>
                <div><span>完成时间</span><strong>{displayTime(selectedTask.completed_at)}</strong></div>
                <div><span>迭代次数</span><strong>{selectedTask.iterations}</strong></div>
                <div><span>Token</span><strong>{selectedTask.tokens_used}</strong></div>
              </div>

              {selectedTask.output && (
                <div>
                  <div className="task-section-title">任务输出</div>
                  <div className="task-output task-output-full">{selectedTask.output}</div>
                </div>
              )}
              {selectedTask.error && (
                <div>
                  <div className="task-section-title">错误信息</div>
                  <div className="task-error task-output-full">{selectedTask.error}</div>
                </div>
              )}

              <div className="modal-actions split-actions">
                <div>
                  {selectedTask.conversation_id && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setConversationId(selectedTask.conversation_id)
                        loadMessages(selectedTask.conversation_id!)
                        setSelectedTask(null)
                      }}
                    >
                      查看对话
                    </button>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-ghost danger-text"
                    onClick={handleDeleteTask}
                    disabled={selectedTask.status === 'running'}
                  >
                    删除任务
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={selectedTask.status === 'running'}>
                    保存修改
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {taskModalOpen && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setTaskModalOpen(false) }}>
          <div className="modal-content">
            <div className="modal-header">
              <h3 className="modal-title">新建任务</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setTaskModalOpen(false)}>关闭</button>
            </div>
            <form onSubmit={submitTask} className="task-form">
              <label>
                <span>任务标题</span>
                <input className="form-input" value={taskForm.title} onChange={e => setTaskForm({ ...taskForm, title: e.target.value })} required />
              </label>
              <label>
                <span>任务说明</span>
                <textarea className="form-textarea" value={taskForm.description} onChange={e => setTaskForm({ ...taskForm, description: e.target.value })} />
              </label>
              <div className="form-grid">
                <label>
                  <span>任务类型</span>
                  <select className="form-select" value={taskForm.task_type} onChange={e => setTaskForm({ ...taskForm, task_type: e.target.value as 'immediate' | 'scheduled' })}>
                    <option value="immediate">立即执行</option>
                    <option value="scheduled">定时执行</option>
                  </select>
                </label>
                <label>
                  <span>优先级</span>
                  <select className="form-select" value={taskForm.priority} onChange={e => setTaskForm({ ...taskForm, priority: e.target.value })}>
                    <option value="low">低</option>
                    <option value="normal">普通</option>
                    <option value="high">高</option>
                  </select>
                </label>
              </div>
              {taskForm.task_type === 'scheduled' && (
                <div className="form-grid">
                  <label>
                    <span>执行时间</span>
                    <input className="form-input" type="datetime-local" value={taskForm.next_run_at} onChange={e => setTaskForm({ ...taskForm, next_run_at: e.target.value })} required />
                  </label>
                  <label>
                    <span>重复</span>
                    <select className="form-select" value={taskForm.repeat} onChange={e => setTaskForm({ ...taskForm, repeat: e.target.value as 'none' | 'daily' | 'weekly' })}>
                      <option value="none">不重复</option>
                      <option value="daily">每天</option>
                      <option value="weekly">每周</option>
                    </select>
                  </label>
                </div>
              )}
              <label className="toggle-row">
                <input type="checkbox" checked={taskForm.save_conversation} onChange={e => setTaskForm({ ...taskForm, save_conversation: e.target.checked })} />
                保存任务对话和执行过程
              </label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setTaskModalOpen(false)}>取消</button>
                <button type="submit" className="btn btn-primary">创建</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
