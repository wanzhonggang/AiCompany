import json
from datetime import datetime, timedelta
from typing import Optional, AsyncIterator
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import get_default_model, get_provider, load_llm_config
from .models import Agent, Task, Conversation, Message, AgentToolBinding, TaskStatus
from .schemas import AgentCreate, AgentUpdate, TaskCreate, TaskUpdate
from .agent_runtime.core import AgentRuntime, AgentConfig, AgentEvent
from .agent_runtime.tools.file_tools import ReadFileTool, WriteFileTool, ListDirectoryTool
from .agent_runtime.tools.web_tools import WebSearchTool, WebFetchTool
from .agent_runtime.tools.email_tools import SendEmailTool
from .agent_runtime.tools.browser_tools import (
    BrowserOpenTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserSnapshotTool,
    BrowserCloseTool,
)


# ---- Tool Registry ----
BUILTIN_TOOLS = [
    ReadFileTool(),
    WriteFileTool(),
    ListDirectoryTool(),
    WebSearchTool(),
    WebFetchTool(),
    BrowserOpenTool(),
    BrowserClickTool(),
    BrowserTypeTool(),
    BrowserSnapshotTool(),
    BrowserCloseTool(),
    SendEmailTool(),
]

TOOL_MAP = {t.name: t for t in BUILTIN_TOOLS}


def get_tools_for_agent(agent: Agent) -> list:
    enabled_names = {tb.tool_name for tb in agent.tool_bindings if tb.enabled}
    existing_names = {tb.tool_name for tb in agent.tool_bindings}
    missing_names = set(TOOL_MAP) - existing_names
    if missing_names:
        enabled_names.update(missing_names)
    return [t for name, t in TOOL_MAP.items() if name in enabled_names]


def _validate_agent_model(provider_name: str, model_name: str) -> None:
    provider = get_provider(provider_name)
    if not provider:
        raise ValueError("LLM 供应商不存在")
    if provider.get("status") != "ready":
        raise ValueError("该 LLM 供应商暂未接入运行时")
    if not provider.get("api_key"):
        raise ValueError("该 LLM 供应商尚未配置 API Key")

    config = load_llm_config()
    provider_config = next((p for p in config.get("providers", []) if p.get("name") == provider_name), None)
    model_names = {m.get("name") for m in (provider_config or {}).get("models", [])}
    if model_name and model_name not in model_names:
        raise ValueError("所选模型不属于该供应商")


# ---- Agent CRUD ----
async def create_agent(db: AsyncSession, data: AgentCreate) -> Agent:
    model_name = data.model_name or get_default_model()
    _validate_agent_model(data.provider, model_name)
    agent = Agent(
        name=data.name,
        role=data.role,
        department=data.department,
        system_prompt=data.system_prompt or f"你是{data.name}，职位是{data.role}。请用你的专业技能帮助完成任务。沟通语言为中文。",
        skills=data.skills,
        avatar_color=data.avatar_color,
        provider=data.provider,
        max_iterations=data.max_iterations,
        model_name=model_name,
    )
    for tool in BUILTIN_TOOLS:
        agent.tool_bindings.append(AgentToolBinding(tool_name=tool.name, enabled=True))

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
    next_provider = update_data.get("provider", agent.provider)
    next_model = update_data.get("model_name", agent.model_name)
    if "provider" in update_data or "model_name" in update_data:
        _validate_agent_model(next_provider, next_model)
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


async def get_conversation(
    db: AsyncSession,
    conv_id: str,
    agent_id: Optional[str] = None,
) -> Optional[Conversation]:
    query = select(Conversation).where(Conversation.id == conv_id)
    if agent_id is not None:
        query = query.where(Conversation.agent_id == agent_id)
    result = await db.execute(query)
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
        conv = await get_conversation(db, conv_id, agent_id=agent_id)
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
    agent.status = "working"
    agent.current_task = message[:200]
    agent.updated_at = datetime.utcnow()
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
    try:
        runtime = AgentRuntime(config)
    except Exception as e:
        agent.status = "blocked"
        agent.current_task = None
        agent.updated_at = datetime.utcnow()
        await db.commit()
        yield AgentEvent(type="error", content=f"Agent 初始化失败: {str(e)}")
        return

    # Stream response
    full_response = ""
    final_data = {}
    had_error = False

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
            full_response = ""
        elif event.type == "done":
            final_data = event.data
        elif event.type == "error":
            full_response = f"错误: {event.content}"
            had_error = True
            yield event
            break

        yield event

    # Update agent status
    agent.status = "blocked" if had_error else "idle"
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

    conversation = None
    if data.save_conversation:
        conversation = Conversation(agent_id=agent_id, title=data.title[:200])
        db.add(conversation)
        await db.flush()

    task = Task(
        agent_id=agent_id,
        conversation_id=conversation.id if conversation else None,
        title=data.title,
        description=data.description,
        task_type=data.task_type,
        schedule=data.schedule,
        repeat=data.repeat,
        priority=data.priority,
        save_conversation=data.save_conversation,
        status=TaskStatus.ASSIGNED.value,
        next_run_at=data.next_run_at if data.task_type == "scheduled" else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return task


async def get_agent_tasks(db: AsyncSession, agent_id: str) -> list[Task]:
    result = await db.execute(
        select(Task).where(Task.agent_id == agent_id).order_by(Task.assigned_at.desc())
    )
    return list(result.scalars().all())


async def get_task(db: AsyncSession, task_id: str) -> Optional[Task]:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def update_task(db: AsyncSession, task_id: str, data: TaskUpdate) -> Optional[Task]:
    task = await get_task(db, task_id)
    if not task:
        return None
    if task.status == TaskStatus.RUNNING.value:
        raise ValueError("Running task cannot be edited")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)

    if task.task_type == "immediate":
        task.next_run_at = None
        task.repeat = "none"
        task.schedule = None
    elif task.task_type == "scheduled" and task.next_run_at:
        if task.status in {
            TaskStatus.PENDING.value,
            TaskStatus.COMPLETED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }:
            task.status = TaskStatus.ASSIGNED.value

    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task_id: str) -> bool:
    task = await get_task(db, task_id)
    if not task:
        return False
    if task.status == TaskStatus.RUNNING.value:
        raise ValueError("Running task cannot be deleted")

    await db.execute(
        update(Message)
        .where(Message.task_id == task_id)
        .values(task_id=None)
    )
    await db.delete(task)
    await db.commit()
    return True


def _task_prompt(task: Task) -> str:
    if task.description.strip():
        return f"{task.title}\n\n{task.description}"
    return task.title


def _next_repeat_time(current: datetime, repeat: str) -> datetime | None:
    if repeat == "daily":
        return current + timedelta(days=1)
    if repeat == "weekly":
        return current + timedelta(days=7)
    return None


async def execute_task(task_id: str) -> None:
    from .database import async_session

    async with async_session() as db:
        task = await db.get(Task, task_id)
        if not task or task.status == TaskStatus.RUNNING.value:
            return

        agent = await get_agent(db, task.agent_id)
        if not agent:
            task.status = TaskStatus.FAILED.value
            task.error = "Agent not found"
            await db.commit()
            return

        task.status = TaskStatus.RUNNING.value
        task.error = None
        task.started_at = datetime.utcnow()
        task.last_run_at = task.started_at
        agent.status = "working"
        agent.current_task = task.title[:200]
        agent.updated_at = datetime.utcnow()

        if task.save_conversation and not task.conversation_id:
            conv = Conversation(agent_id=task.agent_id, title=task.title[:200])
            db.add(conv)
            await db.flush()
            task.conversation_id = conv.id

        if task.save_conversation and task.conversation_id:
            db.add(Message(
                conversation_id=task.conversation_id,
                task_id=task.id,
                role="user",
                content=_task_prompt(task),
            ))

        await db.commit()

        tools = get_tools_for_agent(agent)
        config = AgentConfig(
            system_prompt=agent.system_prompt,
            max_iterations=agent.max_iterations,
            provider=agent.provider,
            model_name=agent.model_name,
            tools=tools,
        )

        full_response = ""
        final_data: dict = {}
        had_error = False

        try:
            runtime = AgentRuntime(config)
            async for event in runtime.run_stream(_task_prompt(task), []):
                if event.type == "text_delta":
                    full_response += event.content
                elif event.type == "tool_cycle" and task.save_conversation and task.conversation_id:
                    tool_calls_stored = [
                        {"id": tc["id"], "name": tc["name"], "input": tc["input"]}
                        for tc in event.data.get("tool_calls", [])
                    ]
                    if tool_calls_stored:
                        db.add(Message(
                            conversation_id=task.conversation_id,
                            task_id=task.id,
                            role="assistant",
                            content=event.data.get("assistant_content") or None,
                            tool_calls=tool_calls_stored,
                        ))
                    for tc in event.data.get("tool_calls", []):
                        db.add(Message(
                            conversation_id=task.conversation_id,
                            task_id=task.id,
                            role="tool",
                            content=tc.get("output", ""),
                            tool_call_id=tc["id"],
                        ))
                    full_response = ""
                    await db.commit()
                elif event.type == "done":
                    final_data = event.data
                elif event.type == "error":
                    had_error = True
                    task.error = event.content
                    full_response = f"错误: {event.content}"
                    break
        except Exception as e:
            had_error = True
            task.error = str(e)
            full_response = f"错误: {str(e)}"

        task.output = full_response
        task.iterations = int(final_data.get("iterations", 0) or 0)
        task.tokens_used = int(final_data.get("tokens", 0) or 0)
        task.completed_at = datetime.utcnow()

        if task.task_type == "scheduled":
            next_run = _next_repeat_time(task.completed_at, task.repeat or "none")
            task.next_run_at = next_run
            task.status = TaskStatus.ASSIGNED.value if next_run else (
                TaskStatus.FAILED.value if had_error else TaskStatus.COMPLETED.value
            )
        else:
            task.status = TaskStatus.FAILED.value if had_error else TaskStatus.COMPLETED.value

        if task.save_conversation and task.conversation_id:
            db.add(Message(
                conversation_id=task.conversation_id,
                task_id=task.id,
                role="assistant",
                content=full_response,
                token_count=task.tokens_used,
            ))
            conv = await get_conversation(db, task.conversation_id, agent_id=task.agent_id)
            if conv:
                conv.updated_at = datetime.utcnow()

        agent.status = "blocked" if had_error else "idle"
        agent.current_task = None
        agent.updated_at = datetime.utcnow()
        await db.commit()


async def get_due_scheduled_tasks(db: AsyncSession) -> list[Task]:
    now = datetime.utcnow()
    result = await db.execute(
        select(Task)
        .where(Task.task_type == "scheduled")
        .where(Task.next_run_at.is_not(None))
        .where(Task.next_run_at <= now)
        .where(Task.status.in_([TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value, TaskStatus.COMPLETED.value]))
        .order_by(Task.next_run_at.asc())
        .limit(10)
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
