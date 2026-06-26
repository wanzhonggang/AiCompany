import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  chatWithAgent,
  beginGlobalLoading,
  createAgentIntegration,
  createAgentRoutine,
  createTask,
  deleteAgentIntegration,
  deleteAgentRoutine,
  deleteConversation,
  deleteTask,
  getAgent,
  getAgentIntegrations,
  getAgentProfile,
  getAgentRoutines,
  getAgentTasks,
  getConversations,
  getMessages,
  planTasks,
  renameConversation,
  saveAgentProfile,
  updateAgentIntegration,
  updateAgentRoutine,
  updateTask,
  type Agent,
  type AgentIntegration,
  type AgentProfile,
  type AgentProfileInput,
  type AgentRoutine,
  type IntegrationRequirement,
  type SmartTaskItem,
  type SmartTaskPlan,
  type ChatMessageHistory,
  type Conversation,
  type TaskInfo,
} from '../api/client'
import { formatBeijingDate, formatBeijingTime, toBeijingDate } from '../utils/time'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'error' | 'thinking'
  content: string
  data?: Record<string, unknown>
  toolCalls?: Array<{ id: string; name: string; input: Record<string, unknown> }>
}

type ExecutionStatus = 'active' | 'done' | 'error'
type StreamMode = 'chat' | 'internal_collaboration'

interface ExecutionEvent {
  id: string
  type: string
  title: string
  content: string
  status: ExecutionStatus
  createdAt: string
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

type WorkspaceTab = 'chat' | 'profile' | 'routines' | 'integrations'

type RoutineFormState = {
  title: string
  description: string
  schedule_type: 'daily' | 'weekly' | 'monthly' | 'cron'
  schedule_time: string
  cron_expression: string
  enabled: boolean
  save_conversation: boolean
}

type IntegrationFormState = {
  provider: 'feishu' | 'wecom' | 'qq' | 'wechat' | 'browser' | 'other'
  name: string
  account_label: string
  usage_scenarios: string
  default_targets: string
  access_method: 'api' | 'web' | 'desktop' | 'manual'
  connection_notes: string
  work_rules: string
  approval_rules: string
  credential_hint: string
  api_app_id: string
  api_secret_env: string
  web_url: string
  enabled: boolean
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

const ROUTINE_LABEL: Record<string, string> = {
  daily: '每天',
  weekly: '每周',
  monthly: '每月',
  cron: 'Cron',
}

const INTEGRATION_LABEL: Record<string, string> = {
  feishu: '飞书',
  wecom: '企业微信',
  qq: 'QQ',
  wechat: '微信',
  browser: '浏览器',
  other: '其他',
}

const ACCESS_METHOD_LABEL: Record<string, string> = {
  api: '开放平台 API / 机器人',
  web: '网页登录 / 云文档',
  desktop: '本机客户端',
  manual: '人工协助',
}

function integrationConfigValue(integration: AgentIntegration | null | undefined, key: string): string {
  const value = integration?.config?.[key]
  return typeof value === 'string' ? value : ''
}

const emptyProfile: AgentProfileInput = {
  mission: '',
  responsibilities: '',
  daily_tasks: '',
  sop: '',
  account_notes: '',
  communication_rules: '',
  approval_rules: '',
  work_style: '',
}

function toDatetimeLocal(value: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`
}

function toDatetimeLocalFromIso(value: string | null | undefined) {
  if (!value) return toDatetimeLocal(new Date(Date.now() + 10 * 60 * 1000))
  return toDatetimeLocal(toBeijingDate(value))
}

function displayTime(value: string | null | undefined) {
  return formatBeijingTime(value)
}

function toText(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function limitText(value: unknown, max = 420): string {
  const text = toText(value).trim()
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}

export function AgentChat({
  showToast,
  readOnlyProfile = false,
}: {
  showToast: (msg: string, type: string) => void
  readOnlyProfile?: boolean
}) {
  const { id } = useParams<{ id: string }>()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [executionEvents, setExecutionEvents] = useState<ExecutionEvent[]>([])
  const [input, setInput] = useState('')
  const [inputHeight, setInputHeight] = useState(58)
  const [sending, setSending] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [convs, setConvs] = useState<Conversation[]>([])
  const [tasks, setTasks] = useState<TaskInfo[]>([])
  const [profile, setProfile] = useState<AgentProfile | null>(null)
  const [profileForm, setProfileForm] = useState<AgentProfileInput>(emptyProfile)
  const [routines, setRoutines] = useState<AgentRoutine[]>([])
  const [integrations, setIntegrations] = useState<AgentIntegration[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('chat')
  const [saveConversation, setSaveConversation] = useState(true)
  const [editingTitle, setEditingTitle] = useState<string | null>(null)
  const [titleInput, setTitleInput] = useState('')
  const [taskModalOpen, setTaskModalOpen] = useState(false)
  const [selectedTask, setSelectedTask] = useState<TaskInfo | null>(null)
  const [selectedRoutine, setSelectedRoutine] = useState<AgentRoutine | null>(null)
  const [selectedIntegration, setSelectedIntegration] = useState<AgentIntegration | null>(null)
  const [routineModalOpen, setRoutineModalOpen] = useState(false)
  const [integrationModalOpen, setIntegrationModalOpen] = useState(false)
  const [draftConversation, setDraftConversation] = useState(false)
  const [taskInstruction, setTaskInstruction] = useState('')
  const [taskSubmitting, setTaskSubmitting] = useState(false)
  const [pendingTaskPlan, setPendingTaskPlan] = useState<SmartTaskPlan | null>(null)
  const [requirementValues, setRequirementValues] = useState<Record<string, Record<string, string>>>({})
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
  const [routineForm, setRoutineForm] = useState<RoutineFormState>({
    title: '',
    description: '',
    schedule_type: 'daily',
    schedule_time: '09:00',
    cron_expression: '',
    enabled: true,
    save_conversation: true,
  })
  const [integrationForm, setIntegrationForm] = useState<IntegrationFormState>({
    provider: 'feishu',
    name: '',
    account_label: '',
    usage_scenarios: '',
    default_targets: '',
    access_method: 'api',
    connection_notes: '',
    work_rules: '',
    approval_rules: '',
    credential_hint: '',
    api_app_id: '',
    api_secret_env: '',
    web_url: '',
    enabled: true,
  })
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const initialConversationLoadedRef = useRef<string | null>(null)
  const streamingTextStartedRef = useRef(false)
  const streamToolCallCountRef = useRef(0)
  const streamModeRef = useRef<StreamMode>('chat')
  const taskCreatingRef = useRef(false)

  const appendExecutionEvent = useCallback((
    type: string,
    title: string,
    content: unknown = '',
    status: ExecutionStatus = 'active',
  ) => {
    setExecutionEvents(prev => [
      ...prev.slice(-9),
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        type,
        title,
        content: limitText(content),
        status,
        createdAt: new Date().toISOString(),
      },
    ])
  }, [])

  const setWaitingForClarification = useCallback((content: string) => {
    setExecutionEvents([{
      id: `${Date.now()}-clarification`,
      type: 'clarification',
      title: '等待补充信息',
      content,
      status: 'done',
      createdAt: new Date().toISOString(),
    }])
  }, [])

  const startInputResize = (startY: number) => {
    const startHeight = inputHeight
    const onMove = (clientY: number) => {
      const nextHeight = Math.max(48, Math.min(180, startHeight + startY - clientY))
      setInputHeight(nextHeight)
    }
    const onMouseMove = (event: MouseEvent) => onMove(event.clientY)
    const onTouchMove = (event: TouchEvent) => {
      if (event.touches[0]) onMove(event.touches[0].clientY)
    }
    const stop = () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', stop)
      window.removeEventListener('touchmove', onTouchMove)
      window.removeEventListener('touchend', stop)
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', stop)
    window.addEventListener('touchmove', onTouchMove)
    window.addEventListener('touchend', stop)
  }

  const loadMessages = useCallback(async (convId: string) => {
    try {
      const history = await getMessages(convId)
      const restoredEvents: ExecutionEvent[] = []
      history.forEach((m: ChatMessageHistory) => {
        if (m.tool_calls?.length) {
          m.tool_calls.forEach((toolCall, index) => {
            restoredEvents.push({
              id: `${m.id}-tool-use-${index}`,
              type: 'tool_use',
              title: '历史工具调用',
              content: `${toolCall.name}${toolCall.input ? `：${limitText(toolCall.input, 220)}` : ''}`,
              status: 'done',
              createdAt: m.created_at || new Date().toISOString(),
            })
          })
        }
        if (m.role === 'tool' && m.content) {
          restoredEvents.push({
            id: `${m.id}-tool-result`,
            type: 'tool_result',
            title: '历史工具结果',
            content: limitText(m.content, 420),
            status: 'done',
            createdAt: m.created_at || new Date().toISOString(),
          })
        }
      })
      const msgs: ChatMessage[] = history
        .filter((m: ChatMessageHistory) => m.role !== 'tool' && !['开始分析任务...', '开机分析任务'].includes((m.content || '').trim()))
        .map((m: ChatMessageHistory) => ({
          id: m.id,
          role: m.role as ChatMessage['role'],
          content: m.content,
          toolCalls: m.tool_calls || undefined,
        }))
      setMessages(msgs)
      setExecutionEvents(restoredEvents.slice(-12))
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
      if (showError) {
        const [profileData, routineData, integrationData] = await Promise.all([
          getAgentProfile(id),
          getAgentRoutines(id),
          getAgentIntegrations(id),
        ])
        setProfile(profileData)
        setProfileForm({
          mission: profileData.mission || '',
          responsibilities: profileData.responsibilities || '',
          daily_tasks: profileData.daily_tasks || '',
          sop: profileData.sop || '',
          account_notes: profileData.account_notes || '',
          communication_rules: profileData.communication_rules || '',
          approval_rules: profileData.approval_rules || '',
          work_style: profileData.work_style || '',
        })
        setRoutines(routineData)
        setIntegrations(integrationData)
      }
      if (!conversationId && !draftConversation && initialConversationLoadedRef.current !== id && convData.length > 0) {
        initialConversationLoadedRef.current = id
        setConversationId(convData[0].id)
        await loadMessages(convData[0].id)
      }
    } catch {
      if (showError) showToast('加载员工工作台失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [conversationId, draftConversation, id, loadMessages, showToast])

  useEffect(() => {
    initialConversationLoadedRef.current = null
    setConversationId(null)
    setMessages([])
    setExecutionEvents([])
    setDraftConversation(false)
    setActiveTab('chat')
  }, [id])

  useEffect(() => {
    loadWorkspace()
    const timer = window.setInterval(() => loadWorkspace(false), 3000)
    return () => window.clearInterval(timer)
  }, [loadWorkspace])

  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container) return
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
  }, [messages, executionEvents])

  const selectedConversation = useMemo(
    () => convs.find(c => c.id === conversationId) || null,
    [convs, conversationId],
  )

  const scheduledTasks = useMemo(
    () => tasks.filter(task => task.task_type === 'scheduled'),
    [tasks],
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

  const startNewConversation = () => {
    setConversationId(null)
    setMessages([])
    setExecutionEvents([])
    setDraftConversation(true)
    setActiveTab('chat')
  }

  const openConversation = async (cid: string | null) => {
    setConversationId(cid)
    setDraftConversation(!cid)
    setExecutionEvents([])
    setActiveTab('chat')
    if (cid) await loadMessages(cid)
    else setMessages([])
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
        setDraftConversation(false)
        await loadMessages(nextConv.id)
      } else {
        startNewConversation()
      }

      if (id) {
        getAgentTasks(id).then(setTasks).catch(() => {})
      }
      showToast('对话已删除', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '删除对话失败', 'error')
    }
  }

  const handleSend = async () => {
    if (!input.trim() || sending || !id) return
    const originalAgent = agent
    const content = input.trim()
    const transientConversation = !saveConversation

    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content }
    setMessages(prev => [...prev, userMsg])
    setExecutionEvents([])
    streamingTextStartedRef.current = false
    streamToolCallCountRef.current = 0
    streamModeRef.current = 'chat'
    appendExecutionEvent('queued', '已接收任务', content, 'active')
    setInput('')
    setSending(true)
    if (agent) setAgent({ ...agent, status: 'working', current_task: content.slice(0, 200) })

    const assistantId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '' }])

    try {
      appendExecutionEvent('planning', '正在判断意图', '判断这是普通对话、立即任务，还是定时/例行工作。', 'active')
      const plan = await planTasks(id, content, saveConversation)
      if (plan.action === 'task' && plan.tasks.length > 0) {
        if (plan.requirements.length > 0) {
          const initialValues: Record<string, Record<string, string>> = {}
          plan.requirements.forEach((requirement, index) => {
            initialValues[String(index)] = {
              account_label: requirement.account_label || '',
              usage_scenarios: content,
              access_method: requirement.access_method,
            }
          })
          setTaskInstruction(content)
          setRequirementValues(initialValues)
          setPendingTaskPlan(plan)
          setAgent(prev => prev ? { ...prev, status: 'idle', current_task: null } : prev)
          appendExecutionEvent('need_info', '需要补充账号工具', '请在弹框中补齐本次任务需要的账号、登录或 API 信息。', 'active')
          setMessages(prev => prev.map(m =>
            m.id === assistantId
              ? { ...m, content: '这个任务需要先补充账号或工具信息。我已经弹出填写窗口，保存后会自动创建并执行任务。' }
              : m
          ))
          setSending(false)
          return
        }

        await createTasksFromPlan(plan.tasks)
        const scheduledCount = plan.tasks.filter(task => task.task_type === 'scheduled').length
        const immediateCount = plan.tasks.length - scheduledCount
        appendExecutionEvent(
          'task_created',
          '任务已生成',
          `已创建 ${plan.tasks.length} 个任务，其中立即任务 ${immediateCount} 个，定时/例行任务 ${scheduledCount} 个。`,
          'done',
        )
        setMessages(prev => prev.map(m =>
          m.id === assistantId
            ? {
                ...m,
                content: plan.tasks.length > 1
                  ? `我已拆分并创建 ${plan.tasks.length} 个任务。定时任务会显示在“例行工作”里，立即任务会开始执行。`
                  : `${scheduledCount ? '我已创建定时/例行任务，并放到“例行工作”里。' : '我已创建立即任务，并开始执行。'}`,
              }
            : m
        ))
        setAgent(prev => prev ? { ...prev, status: 'idle', current_task: null } : prev)
        setSending(false)
        await loadWorkspace(false)
        return
      }
      if (plan.source === 'internal_collaboration') {
        streamModeRef.current = 'internal_collaboration'
        appendExecutionEvent('internal_collaboration', '内部协作', '已识别为员工之间的通知、委派或对接，将由当前员工直接调度目标员工。', 'done')
      } else {
        appendExecutionEvent('chat_mode', '普通对话', '未识别为工作安排，继续由员工直接回复。', 'done')
      }
    } catch {
      appendExecutionEvent('chat_mode', '继续对话', '任务规划不可用，已切换为直接对话。', 'done')
    }

    abortRef.current = chatWithAgent(
      id,
      content,
      saveConversation ? conversationId : null,
      saveConversation,
      (eventType, data) => {
        const eventData = data.data || {}
        switch (eventType) {
          case 'thinking':
            if (streamModeRef.current === 'internal_collaboration') break
            appendExecutionEvent(eventType, '正在分析', data.content || '正在理解任务目标和可用工具', 'active')
            break
          case 'tool_use':
            streamToolCallCountRef.current += 1
            appendExecutionEvent(
              eventType,
              '准备调用工具',
              eventData.tool_name ? `工具：${eventData.tool_name}` : data.content,
              'active',
            )
            break
          case 'tool_result':
            appendExecutionEvent(
              eventType,
              eventData.running ? '工具执行中' : (eventData.success === false ? '工具返回失败' : '工具返回结果'),
              data.content,
              eventData.success === false ? 'error' : 'active',
            )
            break
          case 'tool_cycle':
            appendExecutionEvent(eventType, '工具步骤完成', data.content || eventData.tool_calls, 'done')
            break
          case 'text_delta':
            if (!streamingTextStartedRef.current && streamToolCallCountRef.current > 0) {
              streamingTextStartedRef.current = true
              appendExecutionEvent(eventType, '正在生成回复', 'AI 已开始输出本次任务结果', 'active')
            }
            setMessages(prev => prev.map(m =>
              m.id === assistantId ? { ...m, content: m.content + data.content } : m
            ))
            break
          case 'done': {
            setAgent(prev => prev ? { ...prev, status: 'idle', current_task: null } : prev)
            const doneData = data.data as Record<string, unknown>
            const { conversation_id } = doneData
            if (saveConversation && conversation_id && !conversationId) {
              setConversationId(conversation_id as string)
              setDraftConversation(false)
            }
            if (saveConversation) {
              getConversations(id).then(setConvs).catch(() => {})
            }
            const finalToolCalls = Array.isArray(doneData.tool_calls) ? doneData.tool_calls.length : 0
            const hasExecutedWork = streamToolCallCountRef.current > 0 || finalToolCalls > 0
            if (hasExecutedWork) {
              appendExecutionEvent(eventType, '执行完成', data.content || '本次任务已结束，结果已写入对话或任务记录。', 'done')
            } else if (streamModeRef.current === 'internal_collaboration') {
              setWaitingForClarification('员工正在向你确认缺失条件，补充后再继续委派或执行。')
            } else {
              setExecutionEvents([])
            }
            setMessages(prev => prev.map(m =>
              m.id === assistantId && !m.content
                ? { ...m, content: '任务已完成。模型没有返回额外文字结果，请查看上方执行进度或左侧任务记录。' }
                : m
            ))
            break
          }
          case 'error':
            appendExecutionEvent(eventType, '执行失败', data.content, 'error')
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
        appendExecutionEvent('connection_error', '连接中断', err, 'error')
        setMessages(prev => [...prev, { id: `${Date.now()}-conn`, role: 'error', content: `连接错误: ${err}` }])
        setAgent(prev => prev ? { ...prev, status: 'blocked', current_task: null } : prev)
        setSending(false)
      },
    )
  }

  const handleStop = () => {
    abortRef.current?.abort()
    appendExecutionEvent('stopped', '已停止', '你已手动停止本次执行。', 'done')
    setSending(false)
    setAgent(prev => prev ? { ...prev, status: 'idle', current_task: null } : prev)
  }

  const createTasksFromPlan = async (plannedTasks: SmartTaskItem[]) => {
    if (!id || plannedTasks.length === 0) return
    for (const task of plannedTasks) {
      await createTask(id, {
        title: task.title,
        description: task.description || task.title,
        task_type: task.task_type,
        schedule: task.task_type === 'scheduled' ? task.schedule || '由AI判断的定时任务' : null,
        repeat: task.task_type === 'scheduled' ? task.repeat : 'none',
        priority: task.priority || 'normal',
        save_conversation: true,
        next_run_at: task.task_type === 'scheduled' ? task.next_run_at : null,
      })
    }
  }

  const submitTask = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!id || !taskInstruction.trim() || taskSubmitting || taskCreatingRef.current) return
    taskCreatingRef.current = true
    setTaskSubmitting(true)
    const stopLoading = beginGlobalLoading('正在分析任务并判断需要的账号工具...')
    try {
      const plan = await planTasks(id, taskInstruction.trim(), true)
      if (plan.action === 'chat' || plan.tasks.length === 0) {
        showToast('这句话更像普通对话，请直接在对话框发送。', 'info')
        return
      }
      if (plan.requirements.length > 0) {
        const initialValues: Record<string, Record<string, string>> = {}
        plan.requirements.forEach((requirement, index) => {
          initialValues[String(index)] = {
            account_label: requirement.account_label || '',
            usage_scenarios: taskInstruction.trim(),
            access_method: requirement.access_method,
          }
        })
        setRequirementValues(initialValues)
        setPendingTaskPlan(plan)
        setTaskModalOpen(false)
        showToast('任务需要补充账号或工具信息，请先填写弹框内容', 'info')
        return
      }
      await createTasksFromPlan(plan.tasks)
      showToast(plan.tasks.length > 1 ? `已拆分并创建 ${plan.tasks.length} 个任务` : '任务已创建并开始执行', 'success')
      setTaskModalOpen(false)
      setTaskInstruction('')
      await loadWorkspace(false)
    } catch (e) {
      showToast(e instanceof Error ? e.message : '创建任务失败', 'error')
    } finally {
      stopLoading()
      taskCreatingRef.current = false
      setTaskSubmitting(false)
    }
  }

  const submitRequirementPlan = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!id || !pendingTaskPlan || taskSubmitting || taskCreatingRef.current) return
    taskCreatingRef.current = true
    setTaskSubmitting(true)
    const stopLoading = beginGlobalLoading('正在保存账号工具并创建任务...')
    try {
      for (const [index, requirement] of pendingTaskPlan.requirements.entries()) {
        const values = requirementValues[String(index)] || {}
        const accountLabel = (values.account_label || requirement.account_label || requirement.name).trim()
        const config: Record<string, unknown> = {
          scope: 'agent_only',
          usage_scenarios: values.usage_scenarios || taskInstruction.trim(),
          default_targets: values.default_targets || '',
          access_method: values.access_method || requirement.access_method,
          connection_notes: values.connection_notes || '',
          work_rules: values.work_rules || '',
          approval_rules: values.approval_rules || '',
          credential_hint: values.credential_hint || '',
          api_app_id: values.api_app_id || '',
          api_secret_env: values.api_secret_env || '',
          web_url: values.web_url || '',
          requirement_reason: requirement.reason,
        }
        await createAgentIntegration(id, {
          provider: requirement.provider,
          name: requirement.name || accountLabel,
          account_label: accountLabel,
          config,
          enabled: true,
        })
      }
      await createTasksFromPlan(pendingTaskPlan.tasks)
      showToast(pendingTaskPlan.tasks.length > 1 ? `账号工具已保存，已创建 ${pendingTaskPlan.tasks.length} 个任务` : '账号工具已保存，任务已开始执行', 'success')
      setPendingTaskPlan(null)
      setRequirementValues({})
      setTaskModalOpen(false)
      setTaskInstruction('')
      await loadWorkspace(false)
    } catch (e) {
      showToast(e instanceof Error ? e.message : '保存账号工具失败', 'error')
    } finally {
      stopLoading()
      taskCreatingRef.current = false
      setTaskSubmitting(false)
    }
  }

  const submitTaskEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTask || !taskEditForm.title.trim()) return
    const stopLoading = beginGlobalLoading('正在保存任务修改...')
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
    } finally {
      stopLoading()
    }
  }

  const handleDeleteTask = async () => {
    if (!selectedTask) return
    if (!confirm(`确定删除任务「${selectedTask.title}」吗？任务记录删除后无法恢复。`)) return
    const stopLoading = beginGlobalLoading('正在删除任务...')
    try {
      await deleteTask(selectedTask.id)
      setTasks(prev => prev.filter(task => task.id !== selectedTask.id))
      setSelectedTask(null)
      showToast('任务已删除', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '删除任务失败', 'error')
    } finally {
      stopLoading()
    }
  }

  const submitProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!id) return
    const stopLoading = beginGlobalLoading('正在保存员工记忆...')
    try {
      const saved = await saveAgentProfile(id, profileForm)
      setProfile(saved)
      showToast('员工记忆已保存，后续任务会自动带上这些内容', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '保存员工记忆失败', 'error')
    } finally {
      stopLoading()
    }
  }

  const openRoutineModal = (routine?: AgentRoutine) => {
    setSelectedRoutine(routine || null)
    setRoutineForm(routine ? {
      title: routine.title,
      description: routine.description || '',
      schedule_type: routine.schedule_type,
      schedule_time: routine.schedule_time || '09:00',
      cron_expression: routine.cron_expression || '',
      enabled: routine.enabled,
      save_conversation: routine.save_conversation,
    } : {
      title: '',
      description: '',
      schedule_type: 'daily',
      schedule_time: '09:00',
      cron_expression: '',
      enabled: true,
      save_conversation: true,
    })
    setRoutineModalOpen(true)
  }

  const submitRoutine = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!id || !routineForm.title.trim()) return
    const stopLoading = beginGlobalLoading(selectedRoutine ? '正在保存例行工作...' : '正在创建例行工作...')
    try {
      const payload = {
        title: routineForm.title.trim(),
        description: routineForm.description.trim(),
        schedule_type: routineForm.schedule_type,
        schedule_time: routineForm.schedule_time,
        cron_expression: routineForm.schedule_type === 'cron' ? routineForm.cron_expression.trim() || null : null,
        enabled: routineForm.enabled,
        save_conversation: routineForm.save_conversation,
      }
      const saved = selectedRoutine
        ? await updateAgentRoutine(id, selectedRoutine.id, payload)
        : await createAgentRoutine(id, payload)
      setRoutines(prev => selectedRoutine ? prev.map(item => item.id === saved.id ? saved : item) : [saved, ...prev])
      setRoutineModalOpen(false)
      showToast(selectedRoutine ? '例行工作已更新' : '例行工作已创建', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '保存例行工作失败', 'error')
    } finally {
      stopLoading()
    }
  }

  const handleDeleteRoutine = async (routine: AgentRoutine) => {
    if (!id || !confirm(`确定删除例行工作「${routine.title}」吗？`)) return
    const stopLoading = beginGlobalLoading('正在删除例行工作...')
    try {
      await deleteAgentRoutine(id, routine.id)
      setRoutines(prev => prev.filter(item => item.id !== routine.id))
      showToast('例行工作已删除', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '删除例行工作失败', 'error')
    } finally {
      stopLoading()
    }
  }

  const openIntegrationModal = (integration?: AgentIntegration) => {
    setSelectedIntegration(integration || null)
    setIntegrationForm(integration ? {
      provider: integration.provider,
      name: integration.name,
      account_label: integration.account_label || '',
      usage_scenarios: integrationConfigValue(integration, 'usage_scenarios'),
      default_targets: integrationConfigValue(integration, 'default_targets'),
      access_method: (integrationConfigValue(integration, 'access_method') as IntegrationFormState['access_method']) || 'api',
      connection_notes: integrationConfigValue(integration, 'connection_notes'),
      work_rules: integrationConfigValue(integration, 'work_rules'),
      approval_rules: integrationConfigValue(integration, 'approval_rules'),
      credential_hint: integrationConfigValue(integration, 'credential_hint'),
      api_app_id: integrationConfigValue(integration, 'api_app_id') || integrationConfigValue(integration, 'app_id'),
      api_secret_env: integrationConfigValue(integration, 'api_secret_env') || integrationConfigValue(integration, 'secret_env'),
      web_url: integrationConfigValue(integration, 'web_url'),
      enabled: integration.enabled,
    } : {
      provider: 'feishu',
      name: '',
      account_label: '',
      usage_scenarios: '',
      default_targets: '',
      access_method: 'api',
      connection_notes: '',
      work_rules: '',
      approval_rules: '',
      credential_hint: '',
      api_app_id: '',
      api_secret_env: '',
      web_url: '',
      enabled: true,
    })
    setIntegrationModalOpen(true)
  }

  const submitIntegration = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!id || !integrationForm.name.trim()) return
    const stopLoading = beginGlobalLoading(selectedIntegration ? '正在保存账号工具...' : '正在添加账号工具...')
    try {
      const config: Record<string, unknown> = {
        scope: 'agent_only',
        usage_scenarios: integrationForm.usage_scenarios.trim(),
        default_targets: integrationForm.default_targets.trim(),
        access_method: integrationForm.access_method,
        connection_notes: integrationForm.connection_notes.trim(),
        work_rules: integrationForm.work_rules.trim(),
        approval_rules: integrationForm.approval_rules.trim(),
        credential_hint: integrationForm.credential_hint.trim(),
        api_app_id: integrationForm.api_app_id.trim(),
        api_secret_env: integrationForm.api_secret_env.trim(),
        web_url: integrationForm.web_url.trim(),
      }
      const payload = {
        provider: integrationForm.provider,
        name: integrationForm.name.trim(),
        account_label: integrationForm.account_label.trim(),
        config,
        enabled: integrationForm.enabled,
      }
      const saved = selectedIntegration
        ? await updateAgentIntegration(id, selectedIntegration.id, payload)
        : await createAgentIntegration(id, payload)
      setIntegrations(prev => selectedIntegration ? prev.map(item => item.id === saved.id ? saved : item) : [saved, ...prev])
      setIntegrationModalOpen(false)
      showToast(selectedIntegration ? '账号工具已更新' : '账号工具已添加', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '保存账号工具失败', 'error')
    } finally {
      stopLoading()
    }
  }

  const handleDeleteIntegration = async (integration: AgentIntegration) => {
    if (!id || !confirm(`确定删除账号工具「${integration.name}」吗？`)) return
    const stopLoading = beginGlobalLoading('正在删除账号工具...')
    try {
      await deleteAgentIntegration(id, integration.id)
      setIntegrations(prev => prev.filter(item => item.id !== integration.id))
      showToast('账号工具已删除', 'success')
    } catch (e) {
      showToast(e instanceof Error ? e.message : '删除账号工具失败', 'error')
    } finally {
      stopLoading()
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
    <div className={`agent-chat-page ${readOnlyProfile ? 'employee-chat-page' : 'admin-agent-chat-page'}`}>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {!readOnlyProfile && <Link to="/office" className="btn btn-ghost btn-sm">← 返回办公室</Link>}
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
        <span className="hint-text">在对话框里直接安排工作</span>
      </div>

      <div className="workspace-tabs">
        {[
          ['chat', '对话执行'],
          ...(!readOnlyProfile ? [['profile', '员工档案']] : []),
          ['routines', '例行工作'],
          ['integrations', '账号与工具'],
        ].map(([key, label]) => (
          <button
            key={key}
            className={activeTab === key ? 'active' : ''}
            onClick={() => setActiveTab(key as WorkspaceTab)}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'chat' && (
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
                {task.status === 'running' && <div className="task-progress-note">正在执行，系统会自动刷新任务结果...</div>}
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
                      openConversation(task.conversation_id!)
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
                await openConversation(cid)
              }}
            >
              <option value="">{draftConversation ? '新对话（未保存）' : '新临时对话'}</option>
              {convs.map(c => (
                <option key={c.id} value={c.id}>{c.title} · {formatBeijingDate(c.updated_at || c.created_at)}</option>
              ))}
            </select>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                startNewConversation()
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
            <div className="chat-messages" ref={messagesContainerRef}>
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
              {executionEvents.length > 0 && (
                <div className="execution-panel">
                  <div className="execution-header">
                    <div>
                      <span className={`execution-live ${sending ? 'active' : ''}`} />
                      执行进度
                    </div>
                    <span>{sending ? '运行中' : '最近结果'}</span>
                  </div>
                  <div className="execution-list">
                    {executionEvents.map(event => (
                      <div key={event.id} className={`execution-event execution-${event.status}`}>
                        <div className="execution-event-top">
                          <strong>{event.title}</strong>
                          <span>{displayTime(event.createdAt)}</span>
                        </div>
                        {event.content && <div className="execution-event-content">{event.content}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
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
              <div className="chat-input-stack">
                <div
                  className="chat-input-resizer"
                  role="separator"
                  aria-label="调整输入框高度"
                  onMouseDown={e => {
                    e.preventDefault()
                    startInputResize(e.clientY)
                  }}
                  onTouchStart={e => {
                    if (e.touches[0]) startInputResize(e.touches[0].clientY)
                  }}
                >
                  <span />
                </div>
                <textarea
                  className="chat-input"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={`给 ${agent.name} 安排工作或进行简单对话`}
                  style={{ height: inputHeight }}
                  disabled={sending}
                />
              </div>
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
      )}

      {activeTab === 'profile' && !readOnlyProfile && (
        <section className="memory-panel">
          <div className="memory-hero">
            <div>
              <h2>员工记忆 / 档案</h2>
              <p>这些内容会注入到 {agent.name} 每次对话、任务和例行工作执行的 prompt 中。</p>
            </div>
            {profile?.updated_at && <span>上次更新：{displayTime(profile.updated_at)}</span>}
          </div>
          <form onSubmit={submitProfile} className="profile-grid">
            <label>
              <span>职责定位</span>
              <textarea className="form-textarea" value={profileForm.mission} onChange={e => setProfileForm({ ...profileForm, mission: e.target.value })} placeholder="这个员工在公司里的核心使命和边界" />
            </label>
            <label>
              <span>职责清单</span>
              <textarea className="form-textarea" value={profileForm.responsibilities} onChange={e => setProfileForm({ ...profileForm, responsibilities: e.target.value })} placeholder="负责哪些业务、指标、协作对象" />
            </label>
            <label>
              <span>每日任务</span>
              <textarea className="form-textarea" value={profileForm.daily_tasks} onChange={e => setProfileForm({ ...profileForm, daily_tasks: e.target.value })} placeholder="每天固定要检查、汇报、推进的事项" />
            </label>
            <label>
              <span>工作 SOP</span>
              <textarea className="form-textarea" value={profileForm.sop} onChange={e => setProfileForm({ ...profileForm, sop: e.target.value })} placeholder="标准流程、交付格式、常用判断规则" />
            </label>
            <label>
              <span>账号信息</span>
              <textarea className="form-textarea" value={profileForm.account_notes} onChange={e => setProfileForm({ ...profileForm, account_notes: e.target.value })} placeholder="飞书、企微、在线表格、店铺后台等账号说明，不建议直接写明文密码" />
            </label>
            <label>
              <span>沟通规则</span>
              <textarea className="form-textarea" value={profileForm.communication_rules} onChange={e => setProfileForm({ ...profileForm, communication_rules: e.target.value })} placeholder="什么时候找谁、用什么格式同步、如何跟其他员工对接" />
            </label>
            <label>
              <span>审批规则</span>
              <textarea className="form-textarea" value={profileForm.approval_rules} onChange={e => setProfileForm({ ...profileForm, approval_rules: e.target.value })} placeholder="哪些事情需要老板确认，哪些可以自主执行" />
            </label>
            <label>
              <span>工作风格</span>
              <textarea className="form-textarea" value={profileForm.work_style} onChange={e => setProfileForm({ ...profileForm, work_style: e.target.value })} placeholder="回复风格、报告颗粒度、优先级偏好" />
            </label>
            <div className="profile-actions">
              <button type="submit" className="btn btn-primary">保存员工记忆</button>
            </div>
          </form>
        </section>
      )}

      {activeTab === 'routines' && (
        <section className="memory-panel">
          <div className="memory-hero">
            <div>
              <h2>例行工作</h2>
              <p>这里展示通过对话生成的定时任务。用户不用新增例行工作，直接在对话里说“每天/每周/几点做什么”。</p>
            </div>
            <span className="hint-text">由对话自动生成</span>
          </div>
          <div className="routine-grid">
            {scheduledTasks.map(task => (
              <div key={task.id} className={`routine-card task-${task.status}`} role="button" tabIndex={0} onClick={() => openTaskDetail(task)}>
                <div className="routine-card-head">
                  <div>
                    <h3>{task.title}</h3>
                    <p>{task.schedule || '定时任务'} · {TASK_STATUS[task.status] || task.status}</p>
                  </div>
                  <span className="enabled-dot">定时</span>
                </div>
                <div className="routine-desc">{task.description || '暂无说明'}</div>
                <div className="routine-meta">
                  <span>下次：{displayTime(task.next_run_at)}</span>
                  <span>上次：{displayTime(task.last_run_at)}</span>
                </div>
                {task.output && <div className="task-output">{task.output}</div>}
              </div>
            ))}
            {routines.map(routine => (
              <div key={routine.id} className={`routine-card ${routine.enabled ? '' : 'disabled'}`}>
                <div className="routine-card-head">
                  <div>
                    <h3>{routine.title}</h3>
                    <p>{ROUTINE_LABEL[routine.schedule_type]} {routine.schedule_type === 'cron' ? routine.cron_expression : routine.schedule_time}</p>
                  </div>
                  <span className={routine.enabled ? 'enabled-dot' : 'disabled-dot'}>{routine.enabled ? '启用' : '停用'}</span>
                </div>
                <div className="routine-desc">{routine.description || '暂无说明'}</div>
                <div className="routine-meta">
                  <span>下次：{displayTime(routine.next_run_at)}</span>
                  <span>上次：{displayTime(routine.last_run_at)}</span>
                </div>
                <div className="task-actions">
                  <button className="btn btn-secondary btn-sm" onClick={() => openRoutineModal(routine)}>编辑</button>
                  <button className="btn btn-ghost btn-sm danger-text" onClick={() => handleDeleteRoutine(routine)}>删除</button>
                </div>
              </div>
            ))}
            {scheduledTasks.length === 0 && routines.length === 0 && <div className="empty-mini">还没有例行工作。直接在对话里安排“每天/每周/几点执行”的工作即可。</div>}
          </div>
        </section>
      )}

      {activeTab === 'integrations' && (
        <section className="memory-panel">
          <div className="memory-hero">
            <div>
              <h2>账号与工具</h2>
              <p>账号不需要客户提前手动添加。对话里安排工作时如果 AI 判断需要企业微信、飞书、微信、QQ、浏览器或 API，会自动弹框收集并保存到这里。</p>
            </div>
            <span className="hint-text">由任务触发添加</span>
          </div>
          <div className="integration-guide">
            <div>
              <strong>员工独立账号</strong>
              <p>这里登记的是当前 AI 员工自己的账号配置，例如“Gamma 的企业微信”。不会共享给其他 AI 员工。</p>
            </div>
            <div>
              <strong>告诉 AI 用哪个账号</strong>
              <p>写清楚账号身份、使用场景、默认联系人或群、发送规则。员工执行任务时会把这些规则带进 prompt。</p>
            </div>
            <div>
              <strong>接入方式</strong>
              <p>优先 API/机器人；网页和客户端账号只登记登录要求与入口，后续由浏览器或桌面自动化执行。</p>
            </div>
          </div>
          <div className="integration-grid">
            {integrations.map(integration => (
              <div key={integration.id} className={`integration-card ${integration.enabled ? '' : 'disabled'}`}>
                <div>
                  <span className="integration-provider">{INTEGRATION_LABEL[integration.provider]}</span>
                  <h3>{integration.name}</h3>
                  <p>{integration.account_label || '未填写账号身份'}</p>
                </div>
                <div className="integration-detail-list">
                  <div><span>归属</span><strong>仅当前 AI 员工使用</strong></div>
                  <div><span>场景</span><strong>{integrationConfigValue(integration, 'usage_scenarios') || '未填写'}</strong></div>
                  <div><span>默认对象</span><strong>{integrationConfigValue(integration, 'default_targets') || '未填写'}</strong></div>
                  <div><span>接入</span><strong>{ACCESS_METHOD_LABEL[integrationConfigValue(integration, 'access_method')] || '未填写'}</strong></div>
                </div>
                {integrationConfigValue(integration, 'work_rules') && (
                  <div className="integration-rule-preview">{integrationConfigValue(integration, 'work_rules')}</div>
                )}
                <div className="task-actions">
                  <button className="btn btn-secondary btn-sm" onClick={() => openIntegrationModal(integration)}>编辑</button>
                  <button className="btn btn-ghost btn-sm danger-text" onClick={() => handleDeleteIntegration(integration)}>删除</button>
                </div>
              </div>
            ))}
            {integrations.length === 0 && <div className="empty-mini">还没有账号工具。等任务需要外部账号时，系统会自动弹框让你补充。</div>}
          </div>
        </section>
      )}

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
                        openConversation(selectedTask.conversation_id!)
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

      {routineModalOpen && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setRoutineModalOpen(false) }}>
          <div className="modal-content">
            <div className="modal-header">
              <h3 className="modal-title">{selectedRoutine ? '编辑例行工作' : '新增例行工作'}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setRoutineModalOpen(false)}>关闭</button>
            </div>
            <form onSubmit={submitRoutine} className="task-form">
              <label>
                <span>标题</span>
                <input className="form-input" value={routineForm.title} onChange={e => setRoutineForm({ ...routineForm, title: e.target.value })} required />
              </label>
              <label>
                <span>执行说明</span>
                <textarea className="form-textarea" value={routineForm.description} onChange={e => setRoutineForm({ ...routineForm, description: e.target.value })} />
              </label>
              <div className="form-grid">
                <label>
                  <span>周期</span>
                  <select className="form-select" value={routineForm.schedule_type} onChange={e => setRoutineForm({ ...routineForm, schedule_type: e.target.value as RoutineFormState['schedule_type'] })}>
                    <option value="daily">每天</option>
                    <option value="weekly">每周</option>
                    <option value="monthly">每月</option>
                    <option value="cron">Cron</option>
                  </select>
                </label>
                <label>
                  <span>执行时间</span>
                  <input className="form-input" type="time" value={routineForm.schedule_time} onChange={e => setRoutineForm({ ...routineForm, schedule_time: e.target.value })} />
                </label>
              </div>
              {routineForm.schedule_type === 'cron' && (
                <label>
                  <span>Cron 表达式</span>
                  <input className="form-input" value={routineForm.cron_expression} onChange={e => setRoutineForm({ ...routineForm, cron_expression: e.target.value })} placeholder="先保存表达式，后续可接专用 cron 解析器" />
                </label>
              )}
              <label className="toggle-row">
                <input type="checkbox" checked={routineForm.enabled} onChange={e => setRoutineForm({ ...routineForm, enabled: e.target.checked })} />
                启用例行工作
              </label>
              <label className="toggle-row">
                <input type="checkbox" checked={routineForm.save_conversation} onChange={e => setRoutineForm({ ...routineForm, save_conversation: e.target.checked })} />
                保存执行对话
              </label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setRoutineModalOpen(false)}>取消</button>
                <button type="submit" className="btn btn-primary">保存</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {integrationModalOpen && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setIntegrationModalOpen(false) }}>
          <div className="modal-content integration-modal">
            <div className="modal-header">
              <h3 className="modal-title">{selectedIntegration ? '编辑账号工具' : '添加账号工具'}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setIntegrationModalOpen(false)}>关闭</button>
            </div>
            <form onSubmit={submitIntegration} className="task-form">
              <div className="form-help-info">
                这个账号只属于当前 AI 员工，不会给其他员工使用。请写清楚账号身份、默认发送对象和使用规则。
              </div>
              <div className="form-grid">
                <label>
                  <span>类型</span>
                  <select className="form-select" value={integrationForm.provider} onChange={e => setIntegrationForm({ ...integrationForm, provider: e.target.value as IntegrationFormState['provider'] })}>
                    <option value="feishu">飞书</option>
                    <option value="wecom">企业微信</option>
                    <option value="qq">QQ</option>
                    <option value="wechat">微信</option>
                    <option value="browser">浏览器</option>
                    <option value="other">其他</option>
                  </select>
                </label>
                <label>
                  <span>账号工具名称</span>
                  <input className="form-input" value={integrationForm.name} onChange={e => setIntegrationForm({ ...integrationForm, name: e.target.value })} placeholder="例如：Gamma 的企业微信" required />
                </label>
              </div>
              <label>
                <span>账号身份</span>
                <input className="form-input" value={integrationForm.account_label} onChange={e => setIntegrationForm({ ...integrationForm, account_label: e.target.value })} placeholder="例如：Gamma 秘书的企业微信、运营部企微机器人、店铺客服号" />
              </label>
              <div className="form-grid">
                <label>
                  <span>使用场景</span>
                  <textarea className="form-textarea" value={integrationForm.usage_scenarios} onChange={e => setIntegrationForm({ ...integrationForm, usage_scenarios: e.target.value })} placeholder="例如：给客户发消息、群内同步日报、发送文件、更新在线表格" />
                </label>
                <label>
                  <span>默认联系人 / 群 / 文档</span>
                  <textarea className="form-textarea" value={integrationForm.default_targets} onChange={e => setIntegrationForm({ ...integrationForm, default_targets: e.target.value })} placeholder="例如：运营一群、老板、财务群、客户 A、日报表链接" />
                </label>
              </div>
              <div className="form-grid">
                <label>
                  <span>接入方式</span>
                  <select className="form-select" value={integrationForm.access_method} onChange={e => setIntegrationForm({ ...integrationForm, access_method: e.target.value as IntegrationFormState['access_method'] })}>
                    <option value="api">开放平台 API / 群机器人</option>
                    <option value="web">网页登录 / 云文档</option>
                    <option value="desktop">本机客户端</option>
                    <option value="manual">人工协助</option>
                  </select>
                </label>
                <label>
                  <span>入口链接</span>
                  <input className="form-input" value={integrationForm.web_url} onChange={e => setIntegrationForm({ ...integrationForm, web_url: e.target.value })} placeholder="企微后台、飞书文档、网页版入口，可留空" />
                </label>
              </div>
              <div className="form-grid">
                <label>
                  <span>App ID / 机器人标识</span>
                  <input className="form-input" value={integrationForm.api_app_id} onChange={e => setIntegrationForm({ ...integrationForm, api_app_id: e.target.value })} placeholder="例如 corp_id、app_id、机器人名称" />
                </label>
                <label>
                  <span>密钥环境变量名</span>
                  <input className="form-input" value={integrationForm.api_secret_env} onChange={e => setIntegrationForm({ ...integrationForm, api_secret_env: e.target.value })} placeholder="例如 WECOM_GAMMA_SECRET，不填明文密码" />
                </label>
              </div>
              <label>
                <span>登录/接入说明</span>
                <textarea className="form-textarea" value={integrationForm.connection_notes} onChange={e => setIntegrationForm({ ...integrationForm, connection_notes: e.target.value })} placeholder="例如：首次使用需要老板在本机浏览器完成扫码登录；发送文件前确认文件路径。" />
              </label>
              <label>
                <span>AI 使用规则</span>
                <textarea className="form-textarea" value={integrationForm.work_rules} onChange={e => setIntegrationForm({ ...integrationForm, work_rules: e.target.value })} placeholder="例如：发送日报默认发到运营一群；客户消息先生成草稿；正式通知前先让我确认。" />
              </label>
              <label>
                <span>审批边界</span>
                <textarea className="form-textarea" value={integrationForm.approval_rules} onChange={e => setIntegrationForm({ ...integrationForm, approval_rules: e.target.value })} placeholder="例如：涉及金额、合同、退款、群发客户消息必须先确认。" />
              </label>
              <label>
                <span>凭据提醒</span>
                <input className="form-input" value={integrationForm.credential_hint} onChange={e => setIntegrationForm({ ...integrationForm, credential_hint: e.target.value })} placeholder="例如：密钥在后端环境变量；网页登录已在 Chrome 保持登录" />
              </label>
              <label className="toggle-row">
                <input type="checkbox" checked={integrationForm.enabled} onChange={e => setIntegrationForm({ ...integrationForm, enabled: e.target.checked })} />
                启用账号工具
              </label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setIntegrationModalOpen(false)}>取消</button>
                <button type="submit" className="btn btn-primary">保存</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {taskModalOpen && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setTaskModalOpen(false) }}>
          <div className="modal-content">
            <div className="modal-header">
              <h3 className="modal-title">安排任务</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setTaskModalOpen(false)}>关闭</button>
            </div>
            <form onSubmit={submitTask} className="task-form">
              <div className="form-help-info">
                直接描述你要这个员工做什么。系统会先判断是一件事还是多件事、立即执行还是定时执行；如果需要企业微信、飞书、网页登录或 API，会先让你补齐账号信息。
              </div>
              <label>
                <span>任务指令</span>
                <textarea
                  className="form-textarea smart-task-textarea"
                  value={taskInstruction}
                  onChange={e => setTaskInstruction(e.target.value)}
                  placeholder="例如：今天下午3点打开浏览器检查淘宝店铺数据，并把结果发到运营群。"
                  required
                />
              </label>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setTaskModalOpen(false)} disabled={taskSubmitting}>取消</button>
                <button type="submit" className="btn btn-primary" disabled={taskSubmitting || !taskInstruction.trim()}>
                  {taskSubmitting ? '分析中...' : '让AI判断并创建'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {pendingTaskPlan && (
        <div className="modal-overlay">
          <div className="modal-content integration-modal">
            <div className="modal-header">
              <div>
                <h3 className="modal-title">补充账号与工具</h3>
                <div className="task-meta">AI 判断这个任务需要外部账号或接入信息，保存后会自动写入当前员工的账号与工具。</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => { setPendingTaskPlan(null); setRequirementValues({}) }} disabled={taskSubmitting}>关闭</button>
            </div>
            <form onSubmit={submitRequirementPlan} className="task-form">
              <div className="planned-task-preview">
                <strong>即将创建的任务</strong>
                {pendingTaskPlan.tasks.map((task, index) => (
                  <div key={`${task.title}-${index}`} className="planned-task-item">
                    <span>{index + 1}</span>
                    <div>
                      <b>{task.title}</b>
                      <p>{task.task_type === 'scheduled' ? '定时任务' : '立即任务'} · {task.description || task.title}</p>
                    </div>
                  </div>
                ))}
              </div>
              {pendingTaskPlan.requirements.map((requirement: IntegrationRequirement, index) => {
                const values = requirementValues[String(index)] || {}
                const setValue = (key: string, value: string) => {
                  setRequirementValues(prev => ({
                    ...prev,
                    [String(index)]: { ...(prev[String(index)] || {}), [key]: value },
                  }))
                }
                return (
                  <div key={`${requirement.provider}-${index}`} className="requirement-card">
                    <div className="requirement-title">
                      <span>{INTEGRATION_LABEL[requirement.provider]}</span>
                      <strong>{requirement.name}</strong>
                    </div>
                    <p>{requirement.reason}</p>
                    {requirement.fields.map(field => (
                      <label key={field.key}>
                        <span>{field.label}{field.required ? ' *' : ''}</span>
                        <input
                          className="form-input"
                          value={values[field.key] || ''}
                          onChange={e => setValue(field.key, e.target.value)}
                          placeholder={field.placeholder}
                          required={field.required}
                        />
                      </label>
                    ))}
                    <label>
                      <span>AI 使用规则</span>
                      <textarea
                        className="form-textarea"
                        value={values.work_rules || ''}
                        onChange={e => setValue('work_rules', e.target.value)}
                        placeholder="例如：发消息前先生成草稿；正式群发前必须确认；默认发到哪个群。"
                      />
                    </label>
                  </div>
                )
              })}
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => { setPendingTaskPlan(null); setRequirementValues({}) }} disabled={taskSubmitting}>取消</button>
                <button type="submit" className="btn btn-primary" disabled={taskSubmitting}>
                  {taskSubmitting ? '保存中...' : '保存账号并创建任务'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
