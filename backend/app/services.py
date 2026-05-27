import json
from datetime import datetime
from typing import Optional, AsyncIterator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import get_default_model
from .models import Agent, Task, Conversation, Message, AgentToolBinding
from .schemas import AgentCreate, AgentUpdate, TaskCreate
from .agent_runtime.core import AgentRuntime, AgentConfig, AgentEvent
from .agent_runtime.tools.file_tools import ReadFileTool, WriteFileTool, ListDirectoryTool
from .agent_runtime.tools.web_tools import WebSearchTool, WebFetchTool
from .agent_runtime.tools.email_tools import SendEmailTool


# ---- Tool Registry ----
BUILTIN_TOOLS = [
    ReadFileTool(),
    WriteFileTool(),
    ListDirectoryTool(),
    WebSearchTool(),
    WebFetchTool(),
    SendEmailTool(),
]

TOOL_MAP = {t.name: t for t in BUILTIN_TOOLS}


def get_tools_for_agent(agent: Agent) -> list:
    enabled_names = {tb.tool_name for tb in agent.tool_bindings if tb.enabled}
    return [t for name, t in TOOL_MAP.items() if name in enabled_names]


# ---- Agent CRUD ----
async def create_agent(db: AsyncSession, data: AgentCreate) -> Agent:
    agent = Agent(
        name=data.name,
        role=data.role,
        department=data.department,
        system_prompt=data.system_prompt or f"你是{data.name}，职位是{data.role}。请用你的专业技能帮助完成任务。沟通语言为中文。",
        skills=data.skills,
        avatar_color=data.avatar_color,
        provider=data.provider,
        max_iterations=data.max_iterations,
        model_name=data.model_name or get_default_model(),
    )
    for tool in BUILTIN_TOOLS:
        binding = AgentToolBinding(agent_id=agent.id, tool_name=tool.name, enabled=True)
        agent.tool_bindings.append(binding)

    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def get_agents(db: AsyncSession) -> list[Agent]:
    result = await db.execute(
        select(Agent).options(selectinload(Agent.tool_bindings)).order_by(Agent.created_at.desc())
    )
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, agent_id: str) -> Optional[Agent]:
    result = await db.execute(
        select(Agent).options(selectinload(Agent.tool_bindings)).where(Agent.id == agent_id)
    )
    return result.scalar_one_or_none()


async def update_agent(db: AsyncSession, agent_id: str, data: AgentUpdate) -> Optional[Agent]:
    agent = await get_agent(db, agent_id)
    if not agent:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)
    agent.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(agent)
    return agent


async def delete_agent(db: AsyncSession, agent_id: str) -> bool:
    agent = await get_agent(db, agent_id)
    if not agent:
        return False
    await db.delete(agent)
    await db.commit()
    return True


# ---- Chat ----
async def create_conversation(db: AsyncSession, agent_id: str) -> Conversation:
    conv = Conversation(agent_id=agent_id, title="新对话")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_conversation(db: AsyncSession, conv_id: str) -> Optional[Conversation]:
    result = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    return result.scalar_one_or_none()


async def get_conversation_messages(db: AsyncSession, conv_id: str) -> list[dict]:
    """Load conversation history in OpenAI-compatible format.

    Ensures every tool message immediately follows its parent assistant message
    with matching tool_calls, regardless of DB insertion order.
    """
    result = await db.execute(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
    )
    msgs = list(result.scalars().all())

    # Build index: tool_call_id → tool message
    tool_msgs_by_call_id: dict[str, Message] = {}
    for m in msgs:
        if m.role == "tool" and m.tool_call_id:
            tool_msgs_by_call_id[m.tool_call_id] = m

    history: list[dict] = []
    seen_tool_call_ids: set[str] = set()

    for m in msgs:
        if m.role == "tool":
            # Only emit tool messages when reached via their parent assistant
            continue

        if m.role == "assistant" and m.tool_calls:
            openai_tool_calls = []
            for tc in m.tool_calls:
                tc_id = tc["id"]
                openai_tool_calls.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("input", {}), ensure_ascii=False),
                    },
                })
            history.append({
                "role": m.role,
                "content": m.content or None,
                "tool_calls": openai_tool_calls,
            })
            # Emit matching tool messages immediately after
            for tc in m.tool_calls:
                tc_id = tc["id"]
                tool_msg = tool_msgs_by_call_id.get(tc_id)
                if tool_msg and tc_id not in seen_tool_call_ids:
                    seen_tool_call_ids.add(tc_id)
                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_msg.tool_call_id or "",
                        "content": tool_msg.content,
                    })
        else:
            history.append({"role": m.role, "content": m.content})

    return history


async def chat_with_agent(
    db: AsyncSession,
    agent_id: str,
    message: str,
    conv_id: Optional[str] = None,
) -> AsyncIterator[AgentEvent]:
    """Main chat entry point: load agent, build runtime, stream response."""
    agent = await get_agent(db, agent_id)
    if not agent:
        yield AgentEvent(type="error", content="Agent not found")
        return

    # Get or create conversation
    if conv_id:
        conv = await get_conversation(db, conv_id)
        if not conv:
            yield AgentEvent(type="error", content="Conversation not found")
            return
    else:
        conv = await create_conversation(db, agent_id)

    # Load history (OpenAI format)
    history = await get_conversation_messages(db, conv_id=conv.id)

    # Save user message
    user_msg = Message(conversation_id=conv.id, role="user", content=message)
    db.add(user_msg)
    await db.commit()

    # Build agent runtime
    tools = get_tools_for_agent(agent)
    config = AgentConfig(
        system_prompt=agent.system_prompt,
        max_iterations=agent.max_iterations,
        provider=agent.provider,
        model_name=agent.model_name,
        tools=tools,
    )
    runtime = AgentRuntime(config)

    # Stream response
    full_response = ""
    final_data = {}

    async for event in runtime.run_stream(message, history):
        if event.type == "text_delta":
            full_response += event.content
        elif event.type == "tool_use":
            pass  # tool usage is tracked in the done event
        elif event.type == "tool_result":
            pass  # tool results are saved below from done event data
        elif event.type == "tool_cycle":
            # Extract tool calls for DB storage
            tool_calls_stored = []
            for tc in event.data.get("tool_calls", []):
                tool_calls_stored.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })

            if tool_calls_stored:
                assistant_tool_msg = Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=event.data.get("assistant_content") or None,
                    tool_calls=tool_calls_stored,
                )
                db.add(assistant_tool_msg)

            for tc in event.data.get("tool_calls", []):
                tool_msg = Message(
                    conversation_id=conv.id,
                    role="tool",
                    content=tc.get("output", ""),
                    tool_call_id=tc["id"],
                )
                db.add(tool_msg)
        elif event.type == "done":
            final_data = event.data
        elif event.type == "error":
            full_response = f"错误: {event.content}"
            yield event
            break

        yield event

    # Update agent status
    agent.status = "idle"
    agent.current_task = None
    agent.updated_at = datetime.utcnow()

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=full_response,
        token_count=final_data.get("tokens", 0),
    )
    db.add(assistant_msg)

    # Update conversation
    conv.updated_at = datetime.utcnow()

    await db.commit()


# ---- Tasks ----
async def create_task(db: AsyncSession, agent_id: str, data: TaskCreate) -> Optional[Task]:
    agent = await get_agent(db, agent_id)
    if not agent:
        return None

    task = Task(
        agent_id=agent_id,
        title=data.title,
        description=data.description,
        priority=data.priority,
    )
    db.add(task)
    agent.status = "working"
    agent.current_task = data.title
    agent.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)

    task.status = "assigned"
    await db.commit()

    return task


async def get_agent_tasks(db: AsyncSession, agent_id: str) -> list[Task]:
    result = await db.execute(
        select(Task).where(Task.agent_id == agent_id).order_by(Task.assigned_at.desc())
    )
    return list(result.scalars().all())


async def get_agent_stats(db: AsyncSession) -> dict:
    result = await db.execute(select(Agent.status, func.count(Agent.id)).group_by(Agent.status))
    counts = {row[0]: row[1] for row in result.all()}
    return {
        "total": sum(counts.values()),
        "working": counts.get("working", 0),
        "idle": counts.get("idle", 0),
        "blocked": counts.get("blocked", 0),
        "completed": counts.get("completed", 0),
    }
