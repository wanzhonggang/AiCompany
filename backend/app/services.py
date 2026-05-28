import json
from datetime import datetime, timedelta
from typing import Optional, AsyncIterator
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .config import get_provider_config, load_llm_config
from .models import (
    Agent,
    Department,
    Task,
    Conversation,
    Message,
    AgentToolBinding,
    AgentProfile,
    AgentRoutine,
    AgentIntegration,
    UserAccount,
    EnterpriseLLMKey,
    OperationLog,
    TaskStatus,
)
from .schemas import (
    AgentCreate,
    AgentUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    TaskCreate,
    TaskUpdate,
    AgentProfileUpdate,
    AgentRoutineCreate,
    AgentRoutineUpdate,
    AgentIntegrationCreate,
    AgentIntegrationUpdate,
)
from .agent_runtime.core import AgentRuntime, AgentConfig, AgentEvent
from .agent_runtime.tools.file_tools import ReadFileTool, WriteFileTool, ListDirectoryTool
from .agent_runtime.tools.web_tools import WebSearchTool, WebFetchTool
from .agent_runtime.tools.email_tools import SendEmailTool
from .agent_runtime.tools.collaboration_tools import DelegateTaskTool
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
    DelegateTaskTool(),
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


async def get_enterprise_llm_key(db: AsyncSession, enterprise_id: str | None, provider_name: str) -> str:
    if not enterprise_id:
        return ""
    result = await db.execute(
        select(EnterpriseLLMKey)
        .where(EnterpriseLLMKey.enterprise_id == enterprise_id)
        .where(EnterpriseLLMKey.provider == provider_name)
    )
    key = result.scalar_one_or_none()
    return key.api_key if key else ""


async def _validate_agent_model(db: AsyncSession, enterprise_id: str | None, provider_name: str, model_name: str) -> None:
    provider = get_provider_config(provider_name)
    if not provider:
        raise ValueError("LLM 供应商不存在")
    if provider.get("status") != "ready":
        raise ValueError("该 LLM 供应商暂未接入运行时")
    if not provider_name or not model_name:
        raise ValueError("未选择模型，不可新增AI员工")
    if not await get_enterprise_llm_key(db, enterprise_id, provider_name):
        raise ValueError("该 LLM 供应商尚未配置 API Key")

    config = load_llm_config()
    provider_config = next((p for p in config.get("providers", []) if p.get("name") == provider_name), None)
    model_names = {m.get("name") for m in (provider_config or {}).get("models", [])}
    if model_name and model_name not in model_names:
        raise ValueError("所选模型不属于该供应商")


async def build_org_context(db: AsyncSession, current_agent: Agent) -> str:
    departments = await get_departments(db, enterprise_id=current_agent.enterprise_id)
    agents = await get_agents(db, enterprise_id=current_agent.enterprise_id)
    lines = ["公司组织结构："]
    for dept in departments:
        members = [a for a in agents if (a.department or "未分配") == dept.name]
        member_text = "、".join(f"{a.name}（{a.role}）" for a in members) or "暂无成员"
        lines.append(f"- {dept.name}：{dept.description or '暂无职责说明'}。成员：{member_text}")
    lines.append(
        f"你当前的身份是 {current_agent.name}，部门是 {current_agent.department or '未分配'}，职位是 {current_agent.role}。"
        "当任务需要其他员工或其他部门配合时，请明确指出需要对接的员工/部门、需要交付的信息和下一步动作。"
    )
    memory_context = await build_agent_memory_context(db, current_agent)
    if memory_context:
        lines.append(memory_context)
    return "\n".join(lines)


async def get_agent_profile(db: AsyncSession, agent_id: str) -> Optional[AgentProfile]:
    agent = await db.get(Agent, agent_id)
    if not agent:
        return None
    profile = await db.get(AgentProfile, agent_id)
    if profile:
        return profile
    profile = AgentProfile(agent_id=agent_id)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def log_operation(
    db: AsyncSession,
    actor: UserAccount | None,
    action: str,
    target_type: str,
    target_id: str | None = None,
    target_name: str = "",
    detail: str = "",
) -> None:
    if not actor:
        return
    actor_agent_name = ""
    if actor.agent_id:
        agent = await db.get(Agent, actor.agent_id)
        actor_agent_name = agent.name if agent else ""
    db.add(OperationLog(
        enterprise_id=actor.enterprise_id,
        actor_user_id=actor.id,
        actor_username=actor.username,
        actor_role=actor.role,
        actor_agent_id=actor.agent_id,
        actor_agent_name=actor_agent_name,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        detail=detail,
    ))


async def update_agent_profile(db: AsyncSession, agent_id: str, data: AgentProfileUpdate) -> Optional[AgentProfile]:
    profile = await get_agent_profile(db, agent_id)
    if not profile:
        return None
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    profile.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(profile)
    return profile


def _parse_schedule_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = (value or "09:00").split(":", 1)
        hour = max(0, min(23, int(hour_text)))
        minute = max(0, min(59, int(minute_text)))
        return hour, minute
    except Exception:
        return 9, 0


def _next_routine_time(schedule_type: str, schedule_time: str, from_time: Optional[datetime] = None) -> datetime | None:
    if schedule_type == "cron":
        return None

    base = from_time or datetime.utcnow()
    hour, minute = _parse_schedule_time(schedule_time)
    candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= base:
        if schedule_type == "weekly":
            candidate += timedelta(days=7)
        elif schedule_type == "monthly":
            month = candidate.month + 1
            year = candidate.year
            if month > 12:
                month = 1
                year += 1
            day = min(candidate.day, 28)
            candidate = candidate.replace(year=year, month=month, day=day)
        else:
            candidate += timedelta(days=1)
    return candidate


async def get_agent_routines(db: AsyncSession, agent_id: str) -> list[AgentRoutine]:
    result = await db.execute(
        select(AgentRoutine).where(AgentRoutine.agent_id == agent_id).order_by(AgentRoutine.created_at.desc())
    )
    return list(result.scalars().all())


async def create_agent_routine(db: AsyncSession, agent_id: str, data: AgentRoutineCreate) -> Optional[AgentRoutine]:
    if not await db.get(Agent, agent_id):
        return None
    routine = AgentRoutine(
        agent_id=agent_id,
        title=data.title,
        description=data.description,
        schedule_type=data.schedule_type,
        schedule_time=data.schedule_time,
        cron_expression=data.cron_expression,
        enabled=data.enabled,
        save_conversation=data.save_conversation,
        next_run_at=data.next_run_at or _next_routine_time(data.schedule_type, data.schedule_time),
    )
    db.add(routine)
    await db.commit()
    await db.refresh(routine)
    return routine


async def update_agent_routine(db: AsyncSession, routine_id: str, data: AgentRoutineUpdate) -> Optional[AgentRoutine]:
    routine = await db.get(AgentRoutine, routine_id)
    if not routine:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(routine, key, value)
    if "next_run_at" not in update_data and any(k in update_data for k in ("schedule_type", "schedule_time", "enabled")):
        routine.next_run_at = _next_routine_time(routine.schedule_type, routine.schedule_time) if routine.enabled else None
    routine.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(routine)
    return routine


async def delete_agent_routine(db: AsyncSession, routine_id: str) -> bool:
    routine = await db.get(AgentRoutine, routine_id)
    if not routine:
        return False
    await db.delete(routine)
    await db.commit()
    return True


async def get_agent_integrations(db: AsyncSession, agent_id: str) -> list[AgentIntegration]:
    result = await db.execute(
        select(AgentIntegration).where(AgentIntegration.agent_id == agent_id).order_by(AgentIntegration.created_at.desc())
    )
    return list(result.scalars().all())


async def create_agent_integration(db: AsyncSession, agent_id: str, data: AgentIntegrationCreate) -> Optional[AgentIntegration]:
    if not await db.get(Agent, agent_id):
        return None
    integration = AgentIntegration(
        agent_id=agent_id,
        provider=data.provider,
        name=data.name,
        account_label=data.account_label,
        config=data.config,
        enabled=data.enabled,
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return integration


async def update_agent_integration(db: AsyncSession, integration_id: str, data: AgentIntegrationUpdate) -> Optional[AgentIntegration]:
    integration = await db.get(AgentIntegration, integration_id)
    if not integration:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(integration, key, value)
    integration.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(integration)
    return integration


async def delete_agent_integration(db: AsyncSession, integration_id: str) -> bool:
    integration = await db.get(AgentIntegration, integration_id)
    if not integration:
        return False
    await db.delete(integration)
    await db.commit()
    return True


async def build_agent_memory_context(db: AsyncSession, current_agent: Agent) -> str:
    profile = await db.get(AgentProfile, current_agent.id)
    routines = await get_agent_routines(db, current_agent.id)
    integrations = await get_agent_integrations(db, current_agent.id)

    lines: list[str] = []
    if profile:
        sections = [
            ("职责定位", profile.mission),
            ("职责清单", profile.responsibilities),
            ("每日工作", profile.daily_tasks),
            ("工作 SOP", profile.sop),
            ("账号信息", profile.account_notes),
            ("沟通规则", profile.communication_rules),
            ("审批规则", profile.approval_rules),
            ("工作风格", profile.work_style),
        ]
        for title, content in sections:
            if content and content.strip():
                lines.append(f"{title}：\n{content.strip()}")

    enabled_routines = [r for r in routines if r.enabled]
    if enabled_routines:
        lines.append("例行工作：")
        for routine in enabled_routines[:20]:
            schedule = routine.cron_expression if routine.schedule_type == "cron" else f"{routine.schedule_type} {routine.schedule_time}"
            desc = f"：{routine.description.strip()}" if routine.description and routine.description.strip() else ""
            lines.append(f"- {routine.title}（{schedule}）{desc}")

    enabled_integrations = [i for i in integrations if i.enabled]
    if enabled_integrations:
        lines.append("可用账号与工具：")
        for integration in enabled_integrations[:20]:
            config = integration.config or {}
            config_hint = ", ".join(f"{k}={v}" for k, v in config.items() if v and "key" not in k.lower() and "secret" not in k.lower())
            suffix = f"，配置：{config_hint}" if config_hint else ""
            account = f"，账号：{integration.account_label}" if integration.account_label else ""
            lines.append(f"- {integration.name}（{integration.provider}{account}{suffix}）")

    if not lines:
        return ""
    return "员工长期记忆/档案：\n" + "\n".join(lines)


# ---- Agent CRUD ----
async def ensure_department(
    db: AsyncSession,
    name: str,
    description: str = "",
    color: str = "#06b6d4",
    enterprise_id: Optional[str] = None,
) -> Department:
    clean_name = (name or "未分配").strip() or "未分配"
    query = select(Department).where(Department.name == clean_name)
    if enterprise_id:
        query = query.where(Department.enterprise_id == enterprise_id)
    result = await db.execute(query)
    department = result.scalar_one_or_none()
    if department:
        return department
    if enterprise_id:
        fallback = await db.execute(select(Department).where(Department.name == clean_name))
        department = fallback.scalar_one_or_none()
        if department:
            if not department.enterprise_id:
                department.enterprise_id = enterprise_id
            return department
    department = Department(name=clean_name, description=description, color=color, enterprise_id=enterprise_id)
    db.add(department)
    await db.flush()
    return department


async def get_departments(db: AsyncSession, enterprise_id: Optional[str] = None) -> list[Department]:
    query = select(Department).order_by(Department.created_at.asc())
    if enterprise_id:
        query = query.where(Department.enterprise_id == enterprise_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_department(db: AsyncSession, department_id: str, enterprise_id: Optional[str] = None) -> Optional[Department]:
    department = await db.get(Department, department_id)
    if not department or (enterprise_id and department.enterprise_id != enterprise_id):
        return None
    return department


async def get_department_member_counts(db: AsyncSession, enterprise_id: Optional[str] = None) -> dict[str, int]:
    query = select(Agent.department, func.count(Agent.id)).group_by(Agent.department)
    if enterprise_id:
        query = query.where(Agent.enterprise_id == enterprise_id)
    rows = (await db.execute(query)).all()
    return {row[0] or "未分配": row[1] for row in rows}


async def create_department(db: AsyncSession, data: DepartmentCreate, enterprise_id: Optional[str] = None) -> Department:
    query = select(Department).where(Department.name == data.name.strip())
    if enterprise_id:
        query = query.where(Department.enterprise_id == enterprise_id)
    existing = await db.execute(query)
    if existing.scalar_one_or_none():
        raise ValueError("部门名称已存在")
    department = Department(
        name=data.name.strip(),
        description=data.description,
        color=data.color,
        enterprise_id=enterprise_id,
    )
    db.add(department)
    await db.commit()
    await db.refresh(department)
    return department


async def update_department(
    db: AsyncSession,
    department_id: str,
    data: DepartmentUpdate,
    enterprise_id: Optional[str] = None,
) -> Optional[Department]:
    department = await db.get(Department, department_id)
    if not department or (enterprise_id and department.enterprise_id != enterprise_id):
        return None

    update_data = data.model_dump(exclude_unset=True)
    old_name = department.name
    if "name" in update_data:
        new_name = update_data["name"].strip()
        if not new_name:
            raise ValueError("部门名称不能为空")
        existing_query = select(Department).where(Department.name == new_name, Department.id != department_id)
        if enterprise_id:
            existing_query = existing_query.where(Department.enterprise_id == enterprise_id)
        existing = await db.execute(existing_query)
        if existing.scalar_one_or_none():
            raise ValueError("部门名称已存在")
        update_data["name"] = new_name

    for key, value in update_data.items():
        setattr(department, key, value)
    department.updated_at = datetime.utcnow()

    if "name" in update_data and update_data["name"] != old_name:
        rename_query = update(Agent).where(Agent.department == old_name)
        if enterprise_id:
            rename_query = rename_query.where(Agent.enterprise_id == enterprise_id)
        await db.execute(rename_query.values(department=update_data["name"]))

    await db.commit()
    await db.refresh(department)
    return department


async def delete_department(db: AsyncSession, department_id: str, enterprise_id: Optional[str] = None) -> bool:
    department = await db.get(Department, department_id)
    if not department or (enterprise_id and department.enterprise_id != enterprise_id):
        return False
    member_count_query = select(func.count(Agent.id)).where(Agent.department == department.name)
    if enterprise_id:
        member_count_query = member_count_query.where(Agent.enterprise_id == enterprise_id)
    member_count = (await db.execute(member_count_query)).scalar() or 0
    if member_count > 0:
        raise ValueError("部门下还有员工，不能删除")
    await db.delete(department)
    await db.commit()
    return True


async def create_agent(db: AsyncSession, data: AgentCreate, enterprise_id: Optional[str] = None) -> Agent:
    model_name = (data.model_name or "").strip()
    if not data.provider or not model_name:
        raise ValueError("未选择模型，不可新增AI员工")
    await _validate_agent_model(db, enterprise_id, data.provider, model_name)
    await ensure_department(db, data.department, enterprise_id=enterprise_id)
    agent = Agent(
        enterprise_id=enterprise_id,
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


async def get_agents(db: AsyncSession, enterprise_id: Optional[str] = None) -> list[Agent]:
    query = select(Agent).options(selectinload(Agent.tool_bindings)).order_by(Agent.created_at.desc())
    if enterprise_id:
        query = query.where(Agent.enterprise_id == enterprise_id)
    result = await db.execute(
        query
    )
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, agent_id: str, enterprise_id: Optional[str] = None) -> Optional[Agent]:
    query = select(Agent).options(selectinload(Agent.tool_bindings)).where(Agent.id == agent_id)
    if enterprise_id:
        query = query.where(Agent.enterprise_id == enterprise_id)
    result = await db.execute(
        query
    )
    return result.scalar_one_or_none()


async def update_agent(db: AsyncSession, agent_id: str, data: AgentUpdate, enterprise_id: Optional[str] = None) -> Optional[Agent]:
    agent = await get_agent(db, agent_id, enterprise_id=enterprise_id)
    if not agent:
        return None
    update_data = data.model_dump(exclude_unset=True)
    next_provider = update_data.get("provider", agent.provider)
    next_model = update_data.get("model_name", agent.model_name)
    if "provider" in update_data or "model_name" in update_data:
        await _validate_agent_model(db, enterprise_id, next_provider, next_model)
    if "department" in update_data and update_data["department"] is not None:
        await ensure_department(db, update_data["department"], enterprise_id=enterprise_id)
    for key, value in update_data.items():
        setattr(agent, key, value)
    agent.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(agent)
    return agent


async def delete_agent(db: AsyncSession, agent_id: str, enterprise_id: Optional[str] = None) -> bool:
    agent = await get_agent(db, agent_id, enterprise_id=enterprise_id)
    if not agent:
        return False
    await db.execute(
        update(UserAccount)
        .where(UserAccount.agent_id == agent_id)
        .values(enabled=False, agent_id=None)
    )
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
    org_context = await build_org_context(db, agent)
    config = AgentConfig(
        system_prompt=f"{agent.system_prompt}\n\n{org_context}",
        max_iterations=agent.max_iterations,
        provider=agent.provider,
        model_name=agent.model_name,
        tools=tools,
        agent_id=agent.id,
        api_key=await get_enterprise_llm_key(db, agent.enterprise_id, agent.provider),
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
        org_context = await build_org_context(db, agent)
        config = AgentConfig(
            system_prompt=f"{agent.system_prompt}\n\n{org_context}",
            max_iterations=agent.max_iterations,
            provider=agent.provider,
            model_name=agent.model_name,
            tools=tools,
            agent_id=agent.id,
            api_key=await get_enterprise_llm_key(db, agent.enterprise_id, agent.provider),
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


async def get_assigned_immediate_tasks(db: AsyncSession) -> list[Task]:
    result = await db.execute(
        select(Task)
        .where(Task.task_type == "immediate")
        .where(Task.status == TaskStatus.ASSIGNED.value)
        .order_by(Task.assigned_at.asc())
        .limit(10)
    )
    return list(result.scalars().all())


async def get_due_routines(db: AsyncSession) -> list[AgentRoutine]:
    now = datetime.utcnow()
    result = await db.execute(
        select(AgentRoutine)
        .where(AgentRoutine.enabled == True)  # noqa: E712
        .where(AgentRoutine.next_run_at.is_not(None))
        .where(AgentRoutine.next_run_at <= now)
        .order_by(AgentRoutine.next_run_at.asc())
        .limit(10)
    )
    return list(result.scalars().all())


async def materialize_routine_task(routine_id: str) -> Optional[str]:
    from .database import async_session

    async with async_session() as db:
        routine = await db.get(AgentRoutine, routine_id)
        if not routine or not routine.enabled:
            return None
        agent = await get_agent(db, routine.agent_id)
        if not agent:
            return None

        due_at = routine.next_run_at or datetime.utcnow()
        if due_at > datetime.utcnow():
            return None

        task = Task(
            agent_id=routine.agent_id,
            title=f"例行工作：{routine.title}",
            description=routine.description or routine.title,
            task_type="immediate",
            schedule=f"{routine.schedule_type} {routine.schedule_time}".strip(),
            repeat="none",
            priority="normal",
            save_conversation=routine.save_conversation,
            status=TaskStatus.ASSIGNED.value,
        )
        if routine.save_conversation:
            conversation = Conversation(agent_id=routine.agent_id, title=task.title[:200])
            db.add(conversation)
            await db.flush()
            task.conversation_id = conversation.id

        routine.last_run_at = datetime.utcnow()
        routine.next_run_at = _next_routine_time(routine.schedule_type, routine.schedule_time, routine.last_run_at)
        routine.updated_at = datetime.utcnow()
        db.add(task)
        await db.commit()
        return task.id


async def get_agent_stats(db: AsyncSession, enterprise_id: Optional[str] = None) -> dict:
    query = select(Agent.status, func.count(Agent.id)).group_by(Agent.status)
    if enterprise_id:
        query = query.where(Agent.enterprise_id == enterprise_id)
    result = await db.execute(query)
    counts = {row[0]: row[1] for row in result.all()}
    return {
        "total": sum(counts.values()),
        "working": counts.get("working", 0),
        "idle": counts.get("idle", 0),
        "blocked": counts.get("blocked", 0),
        "completed": counts.get("completed", 0),
    }
