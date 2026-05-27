import { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getAgent, chatWithAgent, getConversations, getMessages, type Agent, type Conversation, type ChatMessageHistory } from '../api/client'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'error' | 'thinking'
  content: string
  data?: Record<string, unknown>
  toolCalls?: Array<{ id: string; name: string; input: Record<string, unknown> }>
}

const STATUS_MAP: Record<string, string> = {
  idle: '空闲中', working: '工作中', blocked: '阻塞中', completed: '已完成',
}

const BASE = '/api';

async function renameConversation(convId: string, title: string): Promise<void> {
  await fetch(`${BASE}/chat/conversations/${convId}/rename`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

export function AgentChat({ showToast }: { showToast: (msg: string, type: string) => void }) {
  const { id } = useParams<{ id: string }>()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [convs, setConvs] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [editingTitle, setEditingTitle] = useState<string | null>(null)
  const [titleInput, setTitleInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const loadAgent = useCallback(async () => {
    if (!id) return
    try {
      const a = await getAgent(id)
      setAgent(a)
      const c = await getConversations(id)
      setConvs(c)
    } catch {
      showToast('加载 Agent 失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { loadAgent() }, [loadAgent])

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    if (!input.trim() || sending || !id) return

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setSending(true)

    // Add a placeholder for the assistant response
    const assistantId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '' }])

    abortRef.current = chatWithAgent(
      id,
      userMsg.content,
      conversationId,
      // onEvent
      (eventType, data) => {
        switch (eventType) {
          case 'thinking':
          case 'tool_use':
            setMessages(prev => [...prev, {
              id: Date.now().toString(),
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
          case 'tool_result':
            setMessages(prev => [...prev, {
              id: Date.now().toString(),
              role: 'tool',
              content: data.content,
              data: data.data,
            }])
            break
          case 'done':
            if (data.data) {
              const { conversation_id } = data.data as Record<string, unknown>
              if (conversation_id && !conversationId) {
                setConversationId(conversation_id as string)
                // Reload conversation list to show the new auto-titled conversation
                getConversations(id!).then(setConvs).catch(() => {})
              }
            }
            // Remove empty assistant message if somehow empty
            setMessages(prev => prev.map(m =>
              m.id === assistantId && !m.content ? { ...m, content: '(任务已完成)' } : m
            ))
            break
          case 'error':
            setMessages(prev => [...prev, {
              id: Date.now().toString(),
              role: 'error',
              content: data.content,
            }])
            break
        }
      },
      // onDone
      () => setSending(false),
      // onError
      (err) => {
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          role: 'error',
          content: `连接错误: ${err}`,
        }])
        setSending(false)
      },
    )
  }

  const handleStop = () => {
    abortRef.current?.abort()
    setSending(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (loading) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>加载中...</div>
  if (!agent) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>Agent 未找到</div>

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link to="/agents" className="btn btn-ghost btn-sm">← 返回</Link>
          <div className="avatar" style={{ background: agent.avatar_color, width: 36, height: 36, fontSize: '0.9rem' }}>
            {agent.name.charAt(0)}
          </div>
          <div>
            <h1 className="page-title" style={{ fontSize: '1.2rem', margin: 0 }}>{agent.name}</h1>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              {agent.role} · <span className={`status-badge status-${agent.status}`} style={{ fontSize: '0.7rem' }}>
                <span className="status-dot" />{STATUS_MAP[agent.status] || agent.status}
              </span>
            </span>
          </div>
        </div>
        {convs.length > 0 && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select
              className="form-select"
              style={{ width: 200 }}
              value={conversationId || ''}
              onChange={async e => {
                const cid = e.target.value || null
                setConversationId(cid)
                if (cid) {
                  setMessages([])
                  await loadMessages(cid)
                } else {
                  setMessages([])
                }
              }}
            >
              <option value="">+ 新对话</option>
              {convs.map(c => (
                <option key={c.id} value={c.id}>{c.title} — {new Date(c.created_at).toLocaleDateString('zh-CN')}</option>
              ))}
            </select>
            {conversationId && (
              <button
                className="btn btn-ghost btn-sm"
                title="重命名对话"
                onClick={() => {
                  const current = convs.find(c => c.id === conversationId)
                  setEditingTitle(conversationId)
                  setTitleInput(current?.title || '')
                }}
              >✎</button>
            )}
          </div>
        )}
        {editingTitle && (
          <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setEditingTitle(null) }}>
            <div className="modal-content" style={{ maxWidth: 380 }}>
              <div className="modal-header">
                <h3 className="modal-title">重命名对话</h3>
                <button className="btn btn-ghost btn-sm" onClick={() => setEditingTitle(null)}>✕</button>
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
      </div>

      <div className="chat-layout">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '2rem', marginBottom: 8 }}>💬</div>
              <div>向 {agent.name} 发送消息开始对话</div>
              <div style={{ fontSize: '0.8rem', marginTop: 8 }}>
                可用工具：读文件 · 写文件 · 列目录 · 搜索网页 · 抓取网页 · 发送邮件
              </div>
            </div>
          )}
          {messages.map(m => (
            <div key={m.id} className={`chat-msg ${m.role}`}>
              {m.content}
            </div>
          ))}
          {sending && <div className="typing-indicator">● ● ● AI 正在思考...</div>}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <textarea
            className="chat-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`向 ${agent.name} 发送消息... (Enter 发送, Shift+Enter 换行)`}
            rows={2}
            disabled={sending}
          />
          {sending ? (
            <button className="btn btn-danger" onClick={handleStop}>⏹ 停止</button>
          ) : (
            <button className="btn btn-primary" onClick={handleSend} disabled={!input.trim()}>
              ➤ 发送
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
