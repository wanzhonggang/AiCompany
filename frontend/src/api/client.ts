const BASE = '/api';

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
  title: string;
  description: string;
  status: string;
  priority: string;
  output: string | null;
  error: string | null;
  iterations: number;
  tokens_used: number;
  assigned_at: string | null;
  completed_at: string | null;
}

// ---- Agents ----
export async function getStats(): Promise<Stats> {
  const r = await fetch(`${BASE}/agents/stats`);
  return r.json();
}

export async function getAgents(): Promise<Agent[]> {
  const r = await fetch(`${BASE}/agents`);
  return r.json();
}

export async function getAgent(id: string): Promise<Agent> {
  const r = await fetch(`${BASE}/agents/${id}`);
  return r.json();
}

export async function createAgent(data: Partial<Agent>): Promise<Agent> {
  const r = await fetch(`${BASE}/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error('Failed to create agent');
  return r.json();
}

export async function updateAgent(id: string, data: Partial<Agent>): Promise<Agent> {
  const r = await fetch(`${BASE}/agents/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return r.json();
}

export async function deleteAgent(id: string): Promise<void> {
  await fetch(`${BASE}/agents/${id}`, { method: 'DELETE' });
}

// ---- Chat (SSE) ----
export function chatWithAgent(
  agentId: string,
  message: string,
  conversationId: string | null,
  onEvent: (event: string, data: { content: string; data: Record<string, unknown> }) => void,
  onDone: () => void,
  onError: (err: string) => void,
): AbortController {
  const controller = new AbortController();

  fetch(`${BASE}/chat/${agentId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
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
  return r.json();
}

// ---- LLM Config ----
export async function getLLMConfig(): Promise<LLMConfig> {
  const r = await fetch(`${BASE}/llm/providers`);
  return r.json();
}

// ---- Tools ----
export async function getTools(): Promise<ToolDef[]> {
  const r = await fetch(`${BASE}/tools`);
  return r.json();
}
