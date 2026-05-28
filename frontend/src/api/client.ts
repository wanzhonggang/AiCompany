const BASE = '/api';
const TOKEN_KEY = 'ai_employee_token';
export const GLOBAL_LOADING_EVENT = 'ai-employee-global-loading';
let loadingDepth = 0;

export function beginGlobalLoading(message: string): () => void {
  loadingDepth += 1;
  window.dispatchEvent(new CustomEvent(GLOBAL_LOADING_EVENT, {
    detail: { active: true, message },
  }));
  let closed = false;
  return () => {
    if (closed) return;
    closed = true;
    loadingDepth = Math.max(0, loadingDepth - 1);
    if (loadingDepth === 0) {
      window.dispatchEvent(new CustomEvent(GLOBAL_LOADING_EVENT, {
        detail: { active: false, message: '' },
      }));
    }
  };
}

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredToken(): string | null {
  return getToken();
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

async function parseJsonResponse<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    let message = fallbackMessage;
    try {
      const body = await response.json();
      message = body?.detail || body?.message || message;
    } catch {
      // Keep fallback message when the server returns non-JSON errors.
    }
    throw new Error(message);
  }
  return response.json();
}

export interface AuthUser {
  id: string;
  username: string;
  role: 'admin' | 'employee';
  enterprise_id: string;
  enterprise_name: string;
  agent_id: string | null;
  display_name: string;
}

export interface AuthResult {
  token: string;
  user: AuthUser;
  payment_required: boolean;
  payment?: Record<string, unknown> | null;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  department: string;
  system_prompt: string;
  status: string;
  current_task: string | null;
  skills: string[];
  avatar_color: string;
  provider: string;
  max_iterations: number;
  model_name: string;
  tool_count: number;
  employee_username: string | null;
  employee_init_password: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProviderInfo {
  name: string;
  display_name: string;
  base_url: string;
  api_key_env: string;
  protocol: string;
  status: string;
  configured: boolean;
  last_refreshed_at?: string | null;
  models: { name: string; display_name: string; description: string }[];
}

export interface LLMConfig {
  providers: ProviderInfo[];
  default_provider: string;
  default_model: string;
  last_model_refresh_at?: string | null;
}

export interface AdminAccount {
  id: string;
  username: string;
  display_name: string;
  enabled: boolean;
  created_at: string | null;
}

export interface OperationLog {
  id: string;
  actor_username: string;
  actor_role: string;
  actor_agent_id: string | null;
  actor_agent_name: string;
  action: string;
  target_type: string;
  target_id: string | null;
  target_name: string;
  detail: string;
  created_at: string | null;
}

export interface Stats {
  total: number;
  working: number;
  idle: number;
  blocked: number;
  completed: number;
}

export interface Conversation {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string | null;
}

export interface ToolDef {
  name: string;
  description: string;
  category: string;
  requires_approval: boolean;
  spec: Record<string, unknown>;
}

export interface Department {
  id: string;
  name: string;
  description: string;
  color: string;
  member_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskInfo {
  id: string;
  agent_id: string;
  conversation_id: string | null;
  title: string;
  description: string;
  status: string;
  task_type: string;
  schedule: string | null;
  repeat: string;
  priority: string;
  save_conversation: boolean;
  output: string | null;
  error: string | null;
  iterations: number;
  tokens_used: number;
  created_at: string | null;
  assigned_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
}

export interface TaskCreateInput {
  title: string;
  description?: string;
  task_type?: 'immediate' | 'scheduled';
  schedule?: string | null;
  repeat?: 'none' | 'daily' | 'weekly';
  priority?: string;
  save_conversation?: boolean;
  next_run_at?: string | null;
}

export type TaskUpdateInput = Partial<TaskCreateInput>;

export interface SmartTaskItem {
  title: string;
  description: string;
  task_type: 'immediate' | 'scheduled';
  schedule: string | null;
  repeat: 'none' | 'daily' | 'weekly';
  priority: string;
  next_run_at: string | null;
}

export interface IntegrationFieldRequirement {
  key: string;
  label: string;
  placeholder: string;
  required: boolean;
}

export interface IntegrationRequirement {
  provider: 'feishu' | 'wecom' | 'qq' | 'wechat' | 'browser' | 'other';
  name: string;
  account_label: string;
  reason: string;
  access_method: 'api' | 'web' | 'desktop' | 'manual';
  fields: IntegrationFieldRequirement[];
}

export interface SmartTaskPlan {
  action: 'chat' | 'task';
  tasks: SmartTaskItem[];
  requirements: IntegrationRequirement[];
  source: string;
}

export interface AgentProfile {
  agent_id: string;
  mission: string;
  responsibilities: string;
  daily_tasks: string;
  sop: string;
  account_notes: string;
  communication_rules: string;
  approval_rules: string;
  work_style: string;
  updated_at: string | null;
}

export type AgentProfileInput = Omit<AgentProfile, 'agent_id' | 'updated_at'>;

export interface AgentRoutine {
  id: string;
  agent_id: string;
  title: string;
  description: string;
  schedule_type: 'daily' | 'weekly' | 'monthly' | 'cron';
  schedule_time: string;
  cron_expression: string | null;
  enabled: boolean;
  save_conversation: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export type AgentRoutineInput = {
  title: string;
  description?: string;
  schedule_type?: 'daily' | 'weekly' | 'monthly' | 'cron';
  schedule_time?: string;
  cron_expression?: string | null;
  enabled?: boolean;
  save_conversation?: boolean;
  next_run_at?: string | null;
};

export interface AgentIntegration {
  id: string;
  agent_id: string;
  provider: 'feishu' | 'wecom' | 'qq' | 'wechat' | 'browser' | 'other';
  name: string;
  account_label: string;
  config: {
    usage_scenario?: string;
    default_recipients?: string;
    access_method?: string;
    approval_rules?: string;
    app_id?: string;
    corp_id?: string;
    secret_env?: string;
    webhook_url?: string;
    login_url?: string;
    notes?: string;
    [key: string]: unknown;
  };
  enabled: boolean;
  last_test_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export type AgentIntegrationInput = {
  provider: 'feishu' | 'wecom' | 'qq' | 'wechat' | 'browser' | 'other';
  name: string;
  account_label?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
};

// ---- Auth ----
export async function registerEnterprise(data: {
  enterprise_name: string;
  admin_username: string;
  admin_password: string;
  plan: 'trial' | 'formal';
  billing_period: 'monthly' | 'yearly';
  payment_method: 'wechat' | 'alipay';
}): Promise<AuthResult> {
  const r = await apiFetch(`${BASE}/auth/register-enterprise`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<AuthResult>(r, '企业注册失败');
}

export async function login(data: { username: string; password: string }): Promise<AuthResult> {
  const r = await apiFetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<AuthResult>(r, '登录失败');
}

export async function getMe(): Promise<AuthUser> {
  const r = await apiFetch(`${BASE}/auth/me`);
  return parseJsonResponse<AuthUser>(r, '获取当前用户失败');
}

export async function changeMyPassword(oldPassword: string, newPassword: string): Promise<void> {
  const r = await apiFetch(`${BASE}/auth/password`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
  await parseJsonResponse<{ ok: boolean }>(r, '修改密码失败');
}

// ---- Admins / Audit ----
export async function getAdmins(): Promise<AdminAccount[]> {
  const r = await apiFetch(`${BASE}/admins`);
  return parseJsonResponse<AdminAccount[]>(r, '加载管理员失败');
}

export async function createAdmin(data: { username: string; password: string; display_name?: string }): Promise<AdminAccount> {
  const r = await apiFetch(`${BASE}/admins`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<AdminAccount>(r, '创建管理员失败');
}

export async function getOperationLogs(limit = 200): Promise<OperationLog[]> {
  const r = await apiFetch(`${BASE}/audit/logs?limit=${limit}`);
  return parseJsonResponse<OperationLog[]>(r, '加载操作记录失败');
}

// ---- Agents ----
export async function getStats(): Promise<Stats> {
  const r = await apiFetch(`${BASE}/agents/stats`);
  return parseJsonResponse<Stats>(r, 'Failed to load stats');
}

export async function getAgents(): Promise<Agent[]> {
  const r = await apiFetch(`${BASE}/agents`);
  return parseJsonResponse<Agent[]>(r, 'Failed to load agents');
}

export async function getAgent(id: string): Promise<Agent> {
  const r = await apiFetch(`${BASE}/agents/${id}`);
  return parseJsonResponse<Agent>(r, 'Failed to load agent');
}

export async function createAgent(data: Partial<Agent>): Promise<Agent> {
  const r = await apiFetch(`${BASE}/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<Agent>(r, 'Failed to create agent');
}

export async function updateAgent(id: string, data: Partial<Agent>): Promise<Agent> {
  const r = await apiFetch(`${BASE}/agents/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<Agent>(r, 'Failed to update agent');
}

export async function deleteAgent(id: string): Promise<void> {
  const r = await apiFetch(`${BASE}/agents/${id}`, { method: 'DELETE' });
  if (!r.ok) throw new Error('Failed to delete agent');
}

export async function updateEmployeePassword(agentId: string, newPassword: string): Promise<{ username?: string | null }> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/employee-password`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password: newPassword }),
  });
  return parseJsonResponse<{ ok: boolean; username?: string | null }>(r, '修改员工密码失败');
}

// ---- Departments ----
export async function getDepartments(): Promise<Department[]> {
  const r = await apiFetch(`${BASE}/departments`);
  return parseJsonResponse<Department[]>(r, 'Failed to load departments');
}

export async function createDepartment(data: Partial<Department>): Promise<Department> {
  const r = await apiFetch(`${BASE}/departments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<Department>(r, 'Failed to create department');
}

export async function updateDepartment(id: string, data: Partial<Department>): Promise<Department> {
  const r = await apiFetch(`${BASE}/departments/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<Department>(r, 'Failed to update department');
}

export async function deleteDepartment(id: string): Promise<void> {
  const r = await apiFetch(`${BASE}/departments/${id}`, { method: 'DELETE' });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to delete department');
}

// ---- Chat (SSE) ----
export function chatWithAgent(
  agentId: string,
  message: string,
  conversationId: string | null,
  saveConversation: boolean,
  onEvent: (event: string, data: { content: string; data: Record<string, unknown> }) => void,
  onDone: () => void,
  onError: (err: string) => void,
): AbortController {
  const controller = new AbortController();

  apiFetch(`${BASE}/chat/${agentId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId, save_conversation: saveConversation }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];
          if (line.startsWith('event: ')) {
            const eventType = line.slice(7).trim();
            const nextLine = lines[i + 1];
            if (nextLine?.startsWith('data: ')) {
              try {
                const data = JSON.parse(nextLine.slice(6));
                onEvent(eventType, data);
              } catch { /* ignore parse errors */ }
              i++; // skip the data line
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message);
      }
    })
    .finally(onDone);

  return controller;
}

export async function getConversations(agentId: string): Promise<Conversation[]> {
  const r = await apiFetch(`${BASE}/chat/conversations/${agentId}`);
  return parseJsonResponse<Conversation[]>(r, 'Failed to load conversations');
}

export async function renameConversation(convId: string, title: string): Promise<void> {
  const r = await apiFetch(`${BASE}/chat/conversations/${convId}/rename`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to rename conversation');
}

export async function deleteConversation(convId: string): Promise<void> {
  const r = await apiFetch(`${BASE}/chat/conversations/${convId}`, { method: 'DELETE' });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to delete conversation');
}

export interface ChatMessageHistory {
  id: string;
  role: string;
  content: string;
  tool_call_id: string | null;
  tool_calls: Array<{ id: string; name: string; input: Record<string, unknown> }> | null;
  created_at: string | null;
}

export async function getMessages(convId: string): Promise<ChatMessageHistory[]> {
  const r = await apiFetch(`${BASE}/chat/messages/${convId}`);
  return parseJsonResponse<ChatMessageHistory[]>(r, 'Failed to load messages');
}

// ---- Tasks ----
export async function getAgentTasks(agentId: string): Promise<TaskInfo[]> {
  const r = await apiFetch(`${BASE}/tasks/agent/${agentId}`);
  return parseJsonResponse<TaskInfo[]>(r, 'Failed to load tasks');
}

export async function createTask(agentId: string, data: TaskCreateInput): Promise<TaskInfo> {
  const r = await apiFetch(`${BASE}/tasks/${agentId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<TaskInfo>(r, 'Failed to create task');
}

export async function planTasks(agentId: string, instruction: string, saveConversation = true): Promise<SmartTaskPlan> {
  const r = await apiFetch(`${BASE}/tasks/${agentId}/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction, save_conversation: saveConversation }),
  });
  return parseJsonResponse<SmartTaskPlan>(r, 'Failed to plan task');
}

export async function updateTask(taskId: string, data: TaskUpdateInput): Promise<TaskInfo> {
  const r = await apiFetch(`${BASE}/tasks/${taskId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<TaskInfo>(r, 'Failed to update task');
}

export async function deleteTask(taskId: string): Promise<void> {
  const r = await apiFetch(`${BASE}/tasks/${taskId}`, { method: 'DELETE' });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to delete task');
}

// ---- Agent memory ----
export async function getAgentProfile(agentId: string): Promise<AgentProfile> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/profile`);
  return parseJsonResponse<AgentProfile>(r, 'Failed to load agent profile');
}

export async function saveAgentProfile(agentId: string, data: AgentProfileInput): Promise<AgentProfile> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<AgentProfile>(r, 'Failed to save agent profile');
}

export async function getAgentRoutines(agentId: string): Promise<AgentRoutine[]> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/routines`);
  return parseJsonResponse<AgentRoutine[]>(r, 'Failed to load routines');
}

export async function createAgentRoutine(agentId: string, data: AgentRoutineInput): Promise<AgentRoutine> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/routines`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<AgentRoutine>(r, 'Failed to create routine');
}

export async function updateAgentRoutine(agentId: string, routineId: string, data: Partial<AgentRoutineInput>): Promise<AgentRoutine> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/routines/${routineId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<AgentRoutine>(r, 'Failed to update routine');
}

export async function deleteAgentRoutine(agentId: string, routineId: string): Promise<void> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/routines/${routineId}`, { method: 'DELETE' });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to delete routine');
}

export async function getAgentIntegrations(agentId: string): Promise<AgentIntegration[]> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/integrations`);
  return parseJsonResponse<AgentIntegration[]>(r, 'Failed to load integrations');
}

export async function createAgentIntegration(agentId: string, data: AgentIntegrationInput): Promise<AgentIntegration> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/integrations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<AgentIntegration>(r, 'Failed to create integration');
}

export async function updateAgentIntegration(agentId: string, integrationId: string, data: Partial<AgentIntegrationInput>): Promise<AgentIntegration> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/integrations/${integrationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<AgentIntegration>(r, 'Failed to update integration');
}

export async function deleteAgentIntegration(agentId: string, integrationId: string): Promise<void> {
  const r = await apiFetch(`${BASE}/agents/${agentId}/integrations/${integrationId}`, { method: 'DELETE' });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to delete integration');
}

// ---- LLM Config ----
export async function getLLMConfig(): Promise<LLMConfig> {
  const r = await apiFetch(`${BASE}/llm/providers`);
  return parseJsonResponse<LLMConfig>(r, 'Failed to load LLM config');
}

export async function saveProviderApiKey(providerName: string, apiKey: string): Promise<void> {
  const r = await apiFetch(`${BASE}/llm/providers/${providerName}/api-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to save API key');
}

export async function setDefaultModel(provider: string, model: string): Promise<void> {
  const r = await apiFetch(`${BASE}/llm/default`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model }),
  });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to set default model');
}

export async function refreshLLMModels(): Promise<LLMConfig & { updated: Array<Record<string, unknown>> }> {
  const r = await apiFetch(`${BASE}/llm/refresh-models`, { method: 'POST' });
  return parseJsonResponse<LLMConfig & { updated: Array<Record<string, unknown>> }>(r, 'Failed to refresh model list');
}

export async function addCustomModel(data: {
  provider: string;
  name: string;
  display_name?: string;
  description?: string;
}): Promise<LLMConfig & { action: string }> {
  const r = await apiFetch(`${BASE}/llm/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<LLMConfig & { action: string }>(r, 'Failed to add custom model');
}

// ---- Tools ----
export async function getTools(): Promise<ToolDef[]> {
  const r = await apiFetch(`${BASE}/tools`);
  return parseJsonResponse<ToolDef[]>(r, 'Failed to load tools');
}
