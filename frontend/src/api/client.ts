const BASE = '/api';

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
  created_at: string | null;
  updated_at: string | null;
}

export interface ProviderInfo {
  name: string;
  display_name: string;
  models: { name: string; display_name: string; description: string }[];
}

export interface LLMConfig {
  providers: ProviderInfo[];
  default_provider: string;
  default_model: string;
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

// ---- Agents ----
export async function getStats(): Promise<Stats> {
  const r = await fetch(`${BASE}/agents/stats`);
  return parseJsonResponse<Stats>(r, 'Failed to load stats');
}

export async function getAgents(): Promise<Agent[]> {
  const r = await fetch(`${BASE}/agents`);
  return parseJsonResponse<Agent[]>(r, 'Failed to load agents');
}

export async function getAgent(id: string): Promise<Agent> {
  const r = await fetch(`${BASE}/agents/${id}`);
  return parseJsonResponse<Agent>(r, 'Failed to load agent');
}

export async function createAgent(data: Partial<Agent>): Promise<Agent> {
  const r = await fetch(`${BASE}/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<Agent>(r, 'Failed to create agent');
}

export async function updateAgent(id: string, data: Partial<Agent>): Promise<Agent> {
  const r = await fetch(`${BASE}/agents/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<Agent>(r, 'Failed to update agent');
}

export async function deleteAgent(id: string): Promise<void> {
  const r = await fetch(`${BASE}/agents/${id}`, { method: 'DELETE' });
  if (!r.ok) throw new Error('Failed to delete agent');
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

  fetch(`${BASE}/chat/${agentId}`, {
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
  const r = await fetch(`${BASE}/chat/conversations/${agentId}`);
  return parseJsonResponse<Conversation[]>(r, 'Failed to load conversations');
}

export async function renameConversation(convId: string, title: string): Promise<void> {
  const r = await fetch(`${BASE}/chat/conversations/${convId}/rename`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  await parseJsonResponse<{ ok: boolean }>(r, 'Failed to rename conversation');
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
  const r = await fetch(`${BASE}/chat/messages/${convId}`);
  return parseJsonResponse<ChatMessageHistory[]>(r, 'Failed to load messages');
}

// ---- Tasks ----
export async function getAgentTasks(agentId: string): Promise<TaskInfo[]> {
  const r = await fetch(`${BASE}/tasks/agent/${agentId}`);
  return parseJsonResponse<TaskInfo[]>(r, 'Failed to load tasks');
}

export async function createTask(agentId: string, data: TaskCreateInput): Promise<TaskInfo> {
  const r = await fetch(`${BASE}/tasks/${agentId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return parseJsonResponse<TaskInfo>(r, 'Failed to create task');
}

// ---- LLM Config ----
export async function getLLMConfig(): Promise<LLMConfig> {
  const r = await fetch(`${BASE}/llm/providers`);
  return parseJsonResponse<LLMConfig>(r, 'Failed to load LLM config');
}

// ---- Tools ----
export async function getTools(): Promise<ToolDef[]> {
  const r = await fetch(`${BASE}/tools`);
  return parseJsonResponse<ToolDef[]>(r, 'Failed to load tools');
}
