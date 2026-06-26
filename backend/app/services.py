import json
import re
from datetime import datetime, timedelta
from typing import Optional, AsyncIterator
from openai import AsyncOpenAI
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
from .agent_runtime.tools.im_tools import (
    WeChatWorkTool,
    FeishuTool,
    QQBotTool,
    WeChatBotTool,
)
from .agent_runtime.tools.browser_tools import (
    BrowserOpenTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserSnapshotTool,
    BrowserCloseTool,
)
from .time_utils import now_beijing, to_beijing_naive


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
    WeChatWorkTool(),
    FeishuTool(),
    QQBotTool(),
    WeChatBotTool(),
]

TOOL_MAP = {t.name: t for t in BUILTIN_TOOLS}
RUNNING_TASK_IDS: set[str] = set()


def describe_changed_fields(update_data: dict, labels: dict[str, str]) -> str:
    changed = [labels.get(key, key) for key, value in update_data.items() if value is not None]
    return "更新字段：" + "、".join(changed) if changed else "提交了更新"


def build_execution_output(full_response: str, final_data: dict) -> str:
    text = (full_response or "").strip()
    if text:
        return text

    tool_calls = final_data.get("tool_calls") or []
    if not tool_calls:
        return "任务已完成，但模型没有返回文本结果。"

    lines = [f"任务已完成，共执行 {len(tool_calls)} 个工具步骤。"]
    for index, tool_call in enumerate(tool_calls[-8:], start=1):
        name = tool_call.get("name") or "unknown_tool"
        status = "成功" if tool_call.get("success") else "失败"
        output = (tool_call.get("output") or "").strip()
        if len(output) > 240:
            output = output[:240] + "..."
        lines.append(f"{index}. {name}：{status}" + (f"\n   结果：{output}" if output else ""))
    return "\n".join(lines)


def _json_from_text(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text or "", re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_provider(value: str) -> str:
    value = (value or "").lower()
    if value in {"feishu", "wecom", "qq", "wechat", "browser", "other"}:
        return value
    if "飞书" in value or "lark" in value:
        return "feishu"
    if "企微" in value or "企业微信" in value or "wecom" in value:
        return "wecom"
    if "qq" in value:
        return "qq"
    if "微信" in value or "wechat" in value:
        return "wechat"
    if "浏览器" in value or "browser" in value:
        return "browser"
    return "other"


def _default_requirement(provider: str, instruction: str) -> dict:
    labels = {
        "feishu": "飞书账号/应用",
        "wecom": "企业微信账号/应用",
        "qq": "QQ账号",
        "wechat": "微信账号",
        "browser": "浏览器登录状态",
        "other": "外部账号或工具",
    }
    access_method = "api" if any(k in instruction.lower() for k in ["api", "appkey", "app key", "secret", "webhook"]) else "web"
    fields = [
        {"key": "account_label", "label": "账号身份", "placeholder": "例如：Gamma 的企业微信、运营部飞书应用", "required": True},
        {"key": "default_targets", "label": "默认联系人/群/文档", "placeholder": "例如：运营一群、老板、客户A、日报表链接", "required": False},
        {"key": "connection_notes", "label": "登录或接入说明", "placeholder": "例如：请先在本机浏览器扫码登录，或说明后台入口", "required": True},
    ]
    if access_method == "api":
        fields.extend([
            {"key": "api_app_id", "label": "App ID / Corp ID / Webhook", "placeholder": "在对应开放平台后台复制", "required": True},
            {"key": "api_secret_env", "label": "密钥环境变量名", "placeholder": "例如 WECOM_GAMMA_SECRET，不要填明文密码", "required": False},
        ])
    else:
        fields.append({"key": "web_url", "label": "网页入口", "placeholder": "例如企业微信后台、飞书云文档链接，可留空", "required": False})
    return {
        "provider": provider,
        "name": labels.get(provider, "外部账号或工具"),
        "account_label": "",
        "reason": "当前任务可能需要使用外部账号或工具，请补齐后再执行。",
        "access_method": access_method,
        "fields": fields,
    }


def _infer_next_run_at(text: str) -> str | None:
    now = now_beijing()
    hour = 9
    minute = 0
    match = re.search(r"(\d{1,2})[:：](\d{2})", text)
    if match:
        hour = max(0, min(23, int(match.group(1))))
        minute = max(0, min(59, int(match.group(2))))
    else:
        hour_match = re.search(r"(上午|下午|晚上|今晚|中午)?\s*(\d{1,2})\s*点", text)
        if hour_match:
            hour = max(0, min(23, int(hour_match.group(2))))
            period = hour_match.group(1) or ""
            if period in {"下午", "晚上", "今晚"} and hour < 12:
                hour += 12
            if period == "中午" and hour < 11:
                hour = 12
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "明天" in text:
        candidate += timedelta(days=1)
    elif candidate <= now:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def _fallback_task_plan(instruction: str) -> dict:
    text = instruction.strip()
    task_keywords = [
        "打开", "检查", "执行", "创建", "生成", "整理", "统计", "发送", "发给", "通知", "安排",
        "对接", "更新", "写", "保存", "放到", "每天", "每日", "每周", "每月", "定时", "明天",
        "下午", "上午", "今晚", "企业微信", "企微", "飞书", "微信", "QQ", "浏览器", "表格",
    ]
    if not any(keyword in text for keyword in task_keywords) and not re.search(r"\d{1,2}[:：]\d{2}", text):
        return {"action": "chat", "tasks": [], "requirements": [], "source": "fallback"}

    separators = r"(?:\n+|；|;|同时|另外|并且|然后)"
    parts = [p.strip(" ，。,.") for p in re.split(separators, text) if p.strip(" ，。,.")]
    if not parts:
        parts = [text]
    if len(parts) > 6:
        parts = [text]

    tasks = []
    for part in parts:
        scheduled = bool(re.search(r"(每天|每日|每周|每月|定时|明天|下午|上午|\d{1,2}[:：]\d{2})", part))
        repeat = "daily" if re.search(r"(每天|每日)", part) else ("weekly" if "每周" in part else "none")
        tasks.append({
            "title": part[:80],
            "description": part,
            "task_type": "scheduled" if scheduled else "immediate",
            "schedule": "由AI根据任务描述判断执行时间" if scheduled else None,
            "repeat": repeat,
            "priority": "normal",
            "next_run_at": _infer_next_run_at(part) if scheduled else None,
        })

    requirements = []
    provider_keywords = [
        ("wecom", ["企业微信", "企微"]),
        ("feishu", ["飞书", "云文档", "在线表格", "表格"]),
        ("wechat", ["微信"]),
        ("qq", ["QQ", "qq"]),
        ("browser", ["浏览器", "网页登录", "网页"]),
    ]
    for provider, keywords in provider_keywords:
        if any(keyword in text for keyword in keywords):
            requirements.append(_default_requirement(provider, text))

    return {"action": "task", "tasks": tasks, "requirements": requirements, "source": "fallback"}


def _looks_like_internal_delegation(
    instruction: str,
    agents: list[Agent],
    departments: list[Department],
    current_agent_id: str,
) -> bool:
    text = instruction.strip().lower()
    if not text:
        return False

    delegation_keywords = [
        "告诉", "通知", "转告", "说下", "说一下", "让", "安排", "派给", "交给", "委派",
        "对接", "转交", "协同", "配合", "问一下", "叫", "找",
    ]
    if not any(keyword in text for keyword in delegation_keywords):
        return False

    target_terms = {"秘书", "员工", "同事", "部门", "主管", "负责人"}
    for agent in agents:
        if agent.id == current_agent_id:
            continue
        for value in (agent.name, agent.role, agent.department):
            value = (value or "").strip().lower()
            if value:
                target_terms.add(value)
                for part in re.split(r"[\s/（()）_-]+", value):
                    if len(part) >= 2:
                        target_terms.add(part)
    for department in departments:
        value = (department.name or "").strip().lower()
        if value:
            target_terms.add(value)

    return any(term and term in text for term in target_terms)


def _normalize_task_plan(raw_plan: dict, instruction: str) -> dict:
    fallback = _fallback_task_plan(instruction)
    raw_tasks = raw_plan.get("tasks") if isinstance(raw_plan, dict) else None
    tasks = []
    for item in (raw_tasks if isinstance(raw_tasks, list) else []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title and not description:
            continue
        task_type = item.get("task_type") if item.get("task_type") in {"immediate", "scheduled"} else "immediate"
        repeat = item.get("repeat") if item.get("repeat") in {"none", "daily", "weekly"} else "none"
        priority = item.get("priority") if item.get("priority") in {"low", "normal", "high"} else "normal"
        tasks.append({
            "title": (title or description)[:200],
            "description": description,
            "task_type": task_type,
            "schedule": item.get("schedule") or None,
            "repeat": repeat,
            "priority": priority,
            "next_run_at": item.get("next_run_at") or (_infer_next_run_at(f"{title} {description}") if task_type == "scheduled" else None),
        })
    action = raw_plan.get("action") if isinstance(raw_plan, dict) else None
    action = action if action in {"chat", "task"} else ("task" if tasks else fallback.get("action", "task"))
    if action == "chat":
        return {"action": "chat", "tasks": [], "requirements": [], "source": raw_plan.get("source", "model")}

    if not tasks:
        tasks = fallback["tasks"]

    requirements = []
    raw_requirements = raw_plan.get("requirements") if isinstance(raw_plan, dict) else None
    for item in (raw_requirements if isinstance(raw_requirements, list) else []):
        if not isinstance(item, dict):
            continue
        provider = _normalize_provider(str(item.get("provider") or "other"))
        req = _default_requirement(provider, instruction)
        req["name"] = str(item.get("name") or req["name"])[:100]
        req["account_label"] = str(item.get("account_label") or "")[:200]
        req["reason"] = str(item.get("reason") or req["reason"])[:500]
        method = str(item.get("access_method") or req["access_method"])
        req["access_method"] = method if method in {"api", "web", "desktop", "manual"} else req["access_method"]
        fields = item.get("fields")
        if isinstance(fields, list) and fields:
            req["fields"] = [
                {
                    "key": str(field.get("key") or "")[:80],
                    "label": str(field.get("label") or field.get("key") or "")[:120],
                    "placeholder": str(field.get("placeholder") or "")[:300],
                    "required": bool(field.get("required")),
                }
                for field in fields
                if isinstance(field, dict) and field.get("key")
            ] or req["fields"]
        requirements.append(req)

    existing_keys = {req["provider"] for req in requirements}
    for req in fallback["requirements"]:
        if req["provider"] not in existing_keys:
            requirements.append(req)

    return {"action": "task", "tasks": tasks[:10], "requirements": requirements[:6], "source": raw_plan.get("source", "model")}


async def plan_agent_tasks(db: AsyncSession, agent_id: str, instruction: str, enterprise_id: Optional[str] = None) -> dict:
    agent = await get_agent(db, agent_id, enterprise_id=enterprise_id)
    if not agent:
        raise ValueError("Agent not found")

    peer_agents = await get_agents(db, enterprise_id=agent.enterprise_id)
    departments = await get_departments(db, enterprise_id=agent.enterprise_id)
    if _looks_like_internal_delegation(instruction, peer_agents, departments, agent.id):
        return {"action": "chat", "tasks": [], "requirements": [], "source": "internal_collaboration"}

    fallback = _fallback_task_plan(instruction)
    api_key = await get_enterprise_llm_key(db, agent.enterprise_id, agent.provider)
    provider = get_provider_config(agent.provider)
    if not provider or not api_key:
        return fallback

    provider = dict(provider)
    provider["api_key"] = api_key
    prompt = f"""
你是企业 AI 员工任务调度器。请把老板的一段自然语言拆成任务计划，并判断是否需要补充外部账号/工具资料。

规则：
0. 先判断用户是不是在安排工作。如果只是寒暄、问答、解释概念、闲聊，返回 action=chat、tasks=[]、requirements=[]。
1. 用户只说一件事，就只能返回 1 个 task；用户明确同时说多件互相独立的事，才拆成多个 task。
2. 判断 task_type：需要未来某个时间/每天/每周执行的是 scheduled，否则 immediate。
3. 如果任务要发企业微信、飞书、微信、QQ、操作在线表格、发文件、打开网页后台、调用 API，而当前信息不足，返回 requirements，让前端弹框给用户补充。
4. 如果不需要外部账号或资料，不要返回 requirements。
5. 只返回 JSON，不要解释。

今天北京时间：{now_beijing().isoformat(timespec="seconds")}
员工：{agent.name} / {agent.department} / {agent.role}
用户指令：{instruction}

JSON 格式：
{{
  "action": "chat 或 task",
  "tasks": [
    {{
      "title": "不超过80字",
      "description": "完整执行说明",
      "task_type": "immediate 或 scheduled",
      "schedule": "定时说明，没有则 null",
      "repeat": "none/daily/weekly",
      "priority": "low/normal/high",
      "next_run_at": "ISO时间或 null"
    }}
  ],
  "requirements": [
    {{
      "provider": "feishu/wecom/qq/wechat/browser/other",
      "name": "账号或工具名称",
      "account_label": "",
      "reason": "为什么需要用户补充",
      "access_method": "api/web/desktop/manual",
      "fields": [
        {{"key":"account_label","label":"账号身份","placeholder":"例如 Gamma 的企业微信","required":true}}
      ]
    }}
  ],
  "source": "model"
}}
"""
    try:
        client = AsyncOpenAI(api_key=provider["api_key"], base_url=provider["base_url"])
        request_kwargs = {
            "model": agent.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if provider.get("extra_body"):
            request_kwargs["extra_body"] = provider["extra_body"]
        response = await client.chat.completions.create(**request_kwargs)
        content = response.choices[0].message.content or ""
        return _normalize_task_plan(_json_from_text(content), instruction)
    except Exception:
        return fallback


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
    return key.get_api_key() if key else ""


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
    enterprise_id: str | None = None,
    actor_agent_id: str | None = None,
    actor_agent_name: str = "",
) -> None:
    if not actor and not enterprise_id:
        return
    log_enterprise_id = actor.enterprise_id if actor else enterprise_id
    actor_username = actor.username if actor else actor_agent_name
    actor_role = actor.role if actor else "employee"
    log_actor_agent_id = actor.agent_id if actor else actor_agent_id
    log_actor_agent_name = actor_agent_name
    if actor and actor.agent_id:
        agent = await db.get(Agent, actor.agent_id)
        log_actor_agent_name = agent.name if agent else ""
    db.add(OperationLog(
        enterprise_id=log_enterprise_id,
        actor_user_id=actor.id if actor else None,
        actor_username=actor_username,
        actor_role=actor_role,
        actor_agent_id=log_actor_agent_id,
        actor_agent_name=log_actor_agent_name,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        detail=detail,
        created_at=now_beijing(),
    ))


async def update_agent_profile(db: AsyncSession, agent_id: str, data: AgentProfileUpdate) -> Optional[AgentProfile]:
    profile = await get_agent_profile(db, agent_id)
    if not profile:
        return None
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    profile.updated_at = now_beijing()
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

    base = from_time or now_beijing()
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
        next_run_at=to_beijing_naive(data.next_run_at) or _next_routine_time(data.schedule_type, data.schedule_time),
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
    if "next_run_at" in update_data:
        update_data["next_run_at"] = to_beijing_naive(update_data["next_run_at"])
    for key, value in update_data.items():
        setattr(routine, key, value)
    if "next_run_at" not in update_data and any(k in update_data for k in ("schedule_type", "schedule_time", "enabled")):
        routine.next_run_at = _next_routine_time(routine.schedule_type, routine.schedule_time) if routine.enabled else None
    routine.updated_at = now_beijing()
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


async def get_agent_integration_configs(db: AsyncSession, agent_id: str) -> dict:
    """Build integration config dict for AgentRuntime: provider -> config dict"""
    integrations = await get_agent_integrations(db, agent_id)
    configs = {}
    for integ in integrations:
        if not integ.enabled:
            continue
        # Map provider names to internal keys
        provider_key = integ.provider
        if provider_key == "wecom":
            provider_key = "wechat_work"
        elif provider_key == "feishu":
            provider_key = "feishu"
        elif provider_key == "qq":
            provider_key = "qq"
        elif provider_key == "wechat":
            provider_key = "wechat"
        configs[provider_key] = integ.config or {}
    return configs


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
    integration.updated_at = now_beijing()
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
        lines.append("可用账号与工具（仅属于当前员工，不与其他员工共享）：")
        for integration in enabled_integrations[:20]:
            config = integration.config or {}
            fields = [
                ("账号身份", integration.account_label),
                ("使用场景", config.get("usage_scenario") or config.get("usage_scenarios")),
                ("默认接收人/群", config.get("default_recipients") or config.get("default_targets")),
                ("接入方式", config.get("access_method")),
                ("连接说明", config.get("connection_notes")),
                ("工作规则", config.get("work_rules")),
                ("审批规则", config.get("approval_rules")),
                ("凭据提示", config.get("credential_hint")),
                ("API 标识", config.get("app_id") or config.get("api_app_id") or config.get("corp_id") or config.get("webhook_url")),
                ("密钥环境变量", config.get("secret_env") or config.get("api_secret_env")),
                ("网页地址", config.get("login_url") or config.get("web_url")),
            ]
            config_hint = "；".join(f"{label}：{value}" for label, value in fields if value)
            suffix = f"，{config_hint}" if config_hint else ""
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
    department.updated_at = now_beijing()

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
    agent.updated_at = now_beijing()
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
    agent.updated_at = now_beijing()
    await db.commit()

    # Build agent runtime
    tools = get_tools_for_agent(agent)
    org_context = await build_org_context(db, agent)
    integration_configs = await get_agent_integration_configs(db, agent.id)
    config = AgentConfig(
        system_prompt=f"{agent.system_prompt}\n\n{org_context}",
        max_iterations=agent.max_iterations,
        provider=agent.provider,
        model_name=agent.model_name,
        tools=tools,
        agent_id=agent.id,
        api_key=await get_enterprise_llm_key(db, agent.enterprise_id, agent.provider),
        integrations=integration_configs,
    )
    try:
        runtime = AgentRuntime(config)
    except Exception as e:
        agent.status = "blocked"
        agent.current_task = None
        agent.updated_at = now_beijing()
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
    agent.updated_at = now_beijing()
    final_output = build_execution_output(full_response, final_data)

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=final_output,
        token_count=final_data.get("tokens", 0),
    )
    db.add(assistant_msg)

    # Update conversation
    conv.updated_at = now_beijing()

    await db.commit()


# ---- Tasks ----
async def create_task(db: AsyncSession, agent_id: str, data: TaskCreate) -> Optional[Task]:
    agent = await get_agent(db, agent_id)
    if not agent:
        return None

    recent_duplicate = await db.execute(
        select(Task)
        .where(Task.agent_id == agent_id)
        .where(Task.title == data.title)
        .where(Task.description == data.description)
        .where(Task.task_type == data.task_type)
        .where(Task.created_at >= now_beijing() - timedelta(seconds=8))
        .order_by(Task.created_at.desc())
    )
    existing_task = recent_duplicate.scalars().first()
    if existing_task:
        return existing_task

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
        next_run_at=to_beijing_naive(data.next_run_at) if data.task_type == "scheduled" else None,
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
    if "next_run_at" in update_data:
        update_data["next_run_at"] = to_beijing_naive(update_data["next_run_at"])
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

    if task_id in RUNNING_TASK_IDS:
        return
    RUNNING_TASK_IDS.add(task_id)
    async with async_session() as db:
        try:
            task = await db.get(Task, task_id)
            if not task or task.status == TaskStatus.RUNNING.value:
                RUNNING_TASK_IDS.discard(task_id)
                return

            agent = await get_agent(db, task.agent_id)
            if not agent:
                task.status = TaskStatus.FAILED.value
                task.error = "Agent not found"
                await db.commit()
                RUNNING_TASK_IDS.discard(task_id)
                return

            task.status = TaskStatus.RUNNING.value
        except Exception:
            RUNNING_TASK_IDS.discard(task_id)
            raise

        task.status = TaskStatus.RUNNING.value
        task.error = None
        task.started_at = now_beijing()
        task.last_run_at = task.started_at
        agent.status = "working"
        agent.current_task = task.title[:200]
        agent.updated_at = now_beijing()

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
        integration_configs = await get_agent_integration_configs(db, agent.id)
        config = AgentConfig(
            system_prompt=f"{agent.system_prompt}\n\n{org_context}",
            max_iterations=agent.max_iterations,
            provider=agent.provider,
            model_name=agent.model_name,
            tools=tools,
            agent_id=agent.id,
            api_key=await get_enterprise_llm_key(db, agent.enterprise_id, agent.provider),
            integrations=integration_configs,
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

        final_output = build_execution_output(full_response, final_data)
        task.output = final_output
        task.iterations = int(final_data.get("iterations", 0) or 0)
        task.tokens_used = int(final_data.get("tokens", 0) or 0)
        task.completed_at = now_beijing()

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
                content=final_output,
                token_count=task.tokens_used,
            ))
            conv = await get_conversation(db, task.conversation_id, agent_id=task.agent_id)
            if conv:
                conv.updated_at = now_beijing()

        agent.status = "blocked" if had_error else "idle"
        agent.current_task = None
        agent.updated_at = now_beijing()
        await db.commit()
        RUNNING_TASK_IDS.discard(task_id)


async def get_due_scheduled_tasks(db: AsyncSession) -> list[Task]:
    now = now_beijing()
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
    now = now_beijing()
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

        due_at = routine.next_run_at or now_beijing()
        if due_at > now_beijing():
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

        routine.last_run_at = now_beijing()
        routine.next_run_at = _next_routine_time(routine.schedule_type, routine.schedule_time, routine.last_run_at)
        routine.updated_at = now_beijing()
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
