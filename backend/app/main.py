import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import get_current_user, require_admin, hash_password
from .config import get_providers_safe, load_llm_config, save_llm_config
from .database import init_db, async_session, get_db
from .routers import agents, chat, tools, tasks, departments, agent_memory, auth, admins, audit, knowledge, workflows, analytics, workstations, downloads
from .middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from .models import Agent, AgentToolBinding, ToolDefinition, Enterprise, UserAccount, Department, EnterpriseLLMKey
from .services import (
    BUILTIN_TOOLS,
    ensure_department,
    execute_task,
    get_assigned_immediate_tasks,
    get_due_scheduled_tasks,
    get_due_routines,
    materialize_routine_task,
    get_enterprise_llm_key,
    log_operation,
)
from .time_utils import now_beijing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from .task_queue import start_task_queue, stop_task_queue

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await seed_data()
    scheduler_task = asyncio.create_task(scheduled_task_loop())
    await start_task_queue()
    logger.info("AI Employee Platform started")
    try:
        yield
    finally:
        scheduler_task.cancel()
        await stop_task_queue()
    # Shutdown


async def scheduled_task_loop():
    while True:
        try:
            async with async_session() as db:
                due_tasks = await get_due_scheduled_tasks(db)
                assigned_tasks = await get_assigned_immediate_tasks(db)
                due_routines = await get_due_routines(db)
            for task in [*due_tasks, *assigned_tasks]:
                asyncio.create_task(execute_task(task.id))
            for routine in due_routines:
                task_id = await materialize_routine_task(routine.id)
                if task_id:
                    asyncio.create_task(execute_task(task_id))
        except Exception as e:
            logger.warning("Scheduled task loop failed: %s", e)
        await asyncio.sleep(30)


async def seed_data():
    """Seed initial agents and keep builtin tool bindings in sync."""
    async with async_session() as db:
        from sqlalchemy import select, func, update

        enterprise = (await db.execute(select(Enterprise).order_by(Enterprise.created_at.asc()))).scalars().first()
        if not enterprise:
            enterprise = Enterprise(
                name="默认企业",
                plan="formal",
                billing_period="monthly",
                payment_status="active",
                expires_at=now_beijing() + timedelta(days=3650),
            )
            db.add(enterprise)
            await db.flush()

            admin = UserAccount(
                enterprise_id=enterprise.id,
                username="admin",
                password_hash=hash_password("admin123"),
                role="admin",
                display_name="默认管理员",
            )
            db.add(admin)
            logger.info("Created default admin account: admin / admin123")

        existing_tool_names = set((await db.execute(select(ToolDefinition.name))).scalars().all())
        for tool in BUILTIN_TOOLS:
            if tool.name not in existing_tool_names:
                db.add(ToolDefinition(
                    name=tool.name,
                    display_name=tool.name,
                    description=tool.description,
                    category=getattr(tool, "category", "general"),
                ))
            else:
                result = await db.execute(select(ToolDefinition).where(ToolDefinition.name == tool.name))
                tool_def = result.scalar_one_or_none()
                if tool_def:
                    tool_def.display_name = tool.name
                    tool_def.description = tool.description
                    tool_def.category = getattr(tool, "category", "general")

        result = await db.execute(select(func.count(Agent.id)))
        agent_count = result.scalar()
        default_departments = [
            ("老板办公室", "负责战略、目标、预算和最终决策。", "#f59e0b"),
            ("运营部", "负责店铺运营、活动计划、日常增长和跨部门协调。", "#10b981"),
            ("市场部", "负责市场调研、竞品分析、内容传播和品牌策略。", "#ec4899"),
            ("技术部", "负责系统开发、自动化、数据接口和技术问题处理。", "#06b6d4"),
            ("数据部", "负责数据分析、报表、指标监控和经营洞察。", "#6366f1"),
            ("综合管理部", "负责行政、文档、流程和日程协同。", "#8b5cf6"),
        ]
        for name, description, color in default_departments:
            await ensure_department(db, name, description, color, enterprise_id=enterprise.id)

        if agent_count == 0:
            logger.info("Seeding initial data...")

            default_provider = load_llm_config().get("default_provider", "deepseek")
            default_model = load_llm_config().get("default_model", "deepseek-chat")
            agents_data = [
                {
                    "name": "Alpha 分析师",
                    "role": "数据分析师",
                    "department": "数据智能部",
                    "system_prompt": "你是 Alpha，一名资深数据分析师。你擅长使用 Python 分析数据、查询数据库、生成可视化报告。你的回答应该专业、数据驱动，用中文沟通。分析数据时优先使用工具读取文件，然后给出深入洞察。",
                    "skills": ["Python", "SQL", "数据分析", "Tableau", "机器学习"],
                    "avatar_color": "#6366f1",
                    "provider": default_provider,
                    "model_name": default_model,
                },
                {
                    "name": "Beta 工程师",
                    "role": "全栈开发工程师",
                    "department": "技术研发部",
                    "system_prompt": "你是 Beta，一名全栈开发工程师。你精通 React、Node.js、PostgreSQL 等技术栈。你可以阅读和编写代码文件，帮助排查问题、重构代码、实现新功能。用中文沟通，代码注释用英文或中文均可。",
                    "skills": ["React", "Node.js", "PostgreSQL", "Docker", "TypeScript"],
                    "avatar_color": "#06b6d4",
                    "provider": default_provider,
                    "model_name": default_model,
                },
                {
                    "name": "Gamma 秘书",
                    "role": "行政秘书",
                    "department": "综合管理部",
                    "system_prompt": "你是 Gamma，一名高效的行政策划秘书。你擅长撰写邮件、整理文档、搜索信息、安排事务。你的回复应该清晰、有条理，善于总结和归纳。当需要发送邮件或搜索信息时，主动使用工具。",
                    "skills": ["邮件撰写", "文档管理", "信息检索", "日程安排"],
                    "avatar_color": "#ec4899",
                    "provider": default_provider,
                    "model_name": default_model,
                },
                {
                    "name": "Delta 研究员",
                    "role": "市场研究员",
                    "department": "市场战略部",
                    "system_prompt": "你是 Delta，一名市场研究员。你擅长搜集行业信息、分析竞品、撰写调研报告。你应该主动使用网络搜索工具获取最新信息，并整理成结构化的分析报告。用中文沟通。",
                    "skills": ["市场调研", "竞品分析", "报告撰写", "数据搜集"],
                    "avatar_color": "#10b981",
                    "provider": default_provider,
                    "model_name": default_model,
                },
            ]

            for ad in agents_data:
                db.add(Agent(**ad, enterprise_id=enterprise.id))
            await db.flush()
        else:
            # Backfill enterprise ownership for existing single-tenant data
            await db.execute(
                update(Agent)
                .where(Agent.enterprise_id.is_(None))
                .values(enterprise_id=enterprise.id)
            )
            await db.execute(
                update(Department)
                .where(Department.enterprise_id.is_(None))
                .values(enterprise_id=enterprise.id)
            )

        agents = (await db.execute(select(Agent).where(Agent.enterprise_id == enterprise.id))).scalars().all()
        for agent in agents:
            await ensure_department(db, agent.department or "未分配", enterprise_id=enterprise.id)
        existing_bindings = {
            (agent_id, tool_name)
            for agent_id, tool_name in (await db.execute(
                select(AgentToolBinding.agent_id, AgentToolBinding.tool_name)
            )).all()
        }
        created_bindings = 0
        for agent in agents:
            for tool in BUILTIN_TOOLS:
                key = (agent.id, tool.name)
                if key not in existing_bindings:
                    db.add(AgentToolBinding(agent_id=agent.id, tool_name=tool.name, enabled=True))
                    created_bindings += 1
        await db.commit()

        if agent_count == 0:
            logger.info(f"Seeded {len(agents)} agents with {len(BUILTIN_TOOLS)} tools each")
        if created_bindings:
            logger.info(f"Added {created_bindings} missing agent tool bindings")


app = FastAPI(title="AI Employee Platform", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=120)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(tools.router)
app.include_router(tasks.router)
app.include_router(departments.router)
app.include_router(agent_memory.router)
app.include_router(auth.router)
app.include_router(admins.router)
app.include_router(audit.router)
app.include_router(knowledge.router)
app.include_router(workflows.router)
app.include_router(analytics.router)
app.include_router(workstations.router)
app.include_router(downloads.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "name": "AI Employee Platform"}


async def _enterprise_configured_providers(db, enterprise_id: str) -> set[str]:
    rows = (await db.execute(
        select(EnterpriseLLMKey.provider).where(EnterpriseLLMKey.enterprise_id == enterprise_id)
    )).scalars().all()
    return set(rows)


async def _enterprise_llm_payload(db, current_user: UserAccount) -> dict:
    config = load_llm_config()
    configured = await _enterprise_configured_providers(db, current_user.enterprise_id)
    enterprise = await db.get(Enterprise, current_user.enterprise_id)
    default_provider = enterprise.default_provider if enterprise else ""
    default_model = enterprise.default_model if enterprise else ""
    if default_provider not in configured:
        default_provider = ""
        default_model = ""
    return {
        "providers": get_providers_safe(configured),
        "default_provider": default_provider,
        "default_model": default_model,
        "last_model_refresh_at": config.get("last_model_refresh_at"),
    }


@app.get("/api/llm/providers")
async def list_providers(
    current_user: UserAccount = Depends(get_current_user),
    db=Depends(get_db),
):
    """Return available LLM providers and models (API keys redacted)."""
    return await _enterprise_llm_payload(db, current_user)


class ProviderKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=4000)


class DefaultModelRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=150)


class CustomModelRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=150)
    display_name: str = Field(default="", max_length=150)
    description: str = Field(default="", max_length=500)


async def _validate_openai_compatible_key(provider: dict, api_key: str) -> tuple[bool, str]:
    if provider.get("status") != "ready":
        return False, "该厂商暂未接入运行时"
    if provider.get("protocol", "openai_compatible") != "openai_compatible":
        return False, "该厂商不是 OpenAI 兼容接口，暂不能直接测试"

    base_url = (provider.get("base_url") or "").rstrip("/")
    if not base_url:
        return False, "厂商缺少 base_url 配置"

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if response.status_code in {401, 403}:
            return False, "API Key 无效或没有权限"
        if response.status_code == 402:
            return True, "API Key 可识别，但账户余额不足"
        if response.status_code >= 400:
            return False, f"厂商校验失败：HTTP {response.status_code}"
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return True, "ok"
        return True, "API Key 已通过连通性测试"
    except httpx.ConnectError:
        return False, "无法连接到厂商接口"
    except httpx.TimeoutException:
        return False, "连接厂商接口超时"
    except Exception as e:
        return False, str(e)


@app.post("/api/llm/providers/{provider_name}/api-key")
async def save_provider_api_key(
    provider_name: str,
    data: ProviderKeyRequest,
    current_user: UserAccount = Depends(require_admin),
    db=Depends(get_db),
):
    config = load_llm_config()
    provider = next((p for p in config.get("providers", []) if p.get("name") == provider_name), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = data.api_key.strip()
    ok, message = await _validate_openai_compatible_key(provider, api_key)
    if not ok:
        raise HTTPException(status_code=400, detail=f"API Key 校验失败：{message}")

    result = await db.execute(
        select(EnterpriseLLMKey)
        .where(EnterpriseLLMKey.enterprise_id == current_user.enterprise_id)
        .where(EnterpriseLLMKey.provider == provider_name)
    )
    key = result.scalar_one_or_none()
    if key:
        key.api_key = api_key
        key.updated_at = now_beijing()
    else:
        db.add(EnterpriseLLMKey(
            enterprise_id=current_user.enterprise_id,
            provider=provider_name,
            api_key=api_key,
        ))

    enterprise = await db.get(Enterprise, current_user.enterprise_id)
    if enterprise and not enterprise.default_provider:
        first_model = next((m.get("name") for m in provider.get("models", []) if m.get("name")), "")
        enterprise.default_provider = provider_name
        enterprise.default_model = first_model
        enterprise.updated_at = now_beijing()
    await log_operation(db, current_user, "保存模型Key", "model_provider", provider_name, provider.get("display_name", provider_name), detail="新增或更新 API Key")
    await db.commit()
    return {"ok": True, "message": message}


@app.patch("/api/llm/default")
async def set_default_model(
    data: DefaultModelRequest,
    current_user: UserAccount = Depends(require_admin),
    db=Depends(get_db),
):
    config = load_llm_config()
    provider = next((p for p in config.get("providers", []) if p.get("name") == data.provider), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    model_names = {m.get("name") for m in provider.get("models", [])}
    if data.model not in model_names:
        raise HTTPException(status_code=404, detail="Model not found")
    if not await get_enterprise_llm_key(db, current_user.enterprise_id, data.provider):
        raise HTTPException(status_code=400, detail="请先配置该厂商 API Key")
    enterprise = await db.get(Enterprise, current_user.enterprise_id)
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    enterprise.default_provider = data.provider
    enterprise.default_model = data.model
    enterprise.updated_at = now_beijing()
    await log_operation(db, current_user, "设置默认模型", "model", data.model, f"{data.provider} / {data.model}", detail="更新默认模型")
    await db.commit()
    return {"ok": True}


@app.post("/api/llm/models")
async def add_custom_model(
    data: CustomModelRequest,
    current_user: UserAccount = Depends(require_admin),
    db=Depends(get_db),
):
    config = load_llm_config()
    provider = next((p for p in config.get("providers", []) if p.get("name") == data.provider), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    model_name = data.name.strip()
    if not model_name:
        raise HTTPException(status_code=422, detail="模型名称不能为空")

    models = provider.setdefault("models", [])
    existing = next((m for m in models if m.get("name") == model_name), None)
    model_data = {
        "name": model_name,
        "display_name": data.display_name.strip() or _format_model_name(model_name),
        "description": data.description.strip() or "用户手动添加的模型",
        "source": "manual",
    }

    if existing:
        existing.update(model_data)
        action = "updated"
    else:
        models.insert(0, model_data)
        action = "created"

    provider["last_refreshed_at"] = now_beijing().isoformat()
    save_llm_config(config)
    await log_operation(
        db,
        current_user,
        "添加模型" if action == "created" else "更新模型",
        "model",
        model_name,
        f"{provider.get('display_name', data.provider)} / {model_name}",
        detail="手动新增模型" if action == "created" else "更新模型名称或说明",
    )
    await db.commit()
    payload = await _enterprise_llm_payload(db, current_user)
    return {
        "ok": True,
        "action": action,
        **payload,
    }


def _format_model_name(model_id: str) -> str:
    cleaned = model_id.split("/")[-1].replace("-", " ").replace("_", " ")
    return " ".join(part.capitalize() if not part.isupper() else part for part in cleaned.split())


def _merge_provider_models(provider: dict, fetched_ids: list[str]) -> int:
    existing = {m.get("name"): dict(m) for m in provider.get("models", [])}
    changed = 0
    merged = []
    seen = set()

    for model_id in fetched_ids:
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        current = existing.get(model_id)
        if current:
            merged.append(current)
        else:
            changed += 1
            merged.append({
                "name": model_id,
                "display_name": _format_model_name(model_id),
                "description": "从厂商 /models 接口同步",
            })

    for model_id, model in existing.items():
        if model_id not in seen:
            merged.append(model)

    provider["models"] = merged
    provider["last_refreshed_at"] = now_beijing().isoformat()
    return changed


@app.post("/api/llm/refresh-models")
async def refresh_models(
    current_user: UserAccount = Depends(require_admin),
    db=Depends(get_db),
):
    """Refresh model choices from configured OpenAI-compatible providers."""
    config = load_llm_config()
    updated: list[dict] = []

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for provider in config.get("providers", []):
            if provider.get("status") != "ready" or provider.get("protocol", "openai_compatible") != "openai_compatible":
                continue
            base_url = (provider.get("base_url") or "").rstrip("/")
            if not base_url:
                continue

            api_key = await get_enterprise_llm_key(db, current_user.enterprise_id, provider.get("name"))
            if not api_key:
                updated.append({
                    "provider": provider.get("name"),
                    "status": "skipped",
                    "reason": "missing_api_key",
                    "added": 0,
                    "total": len(provider.get("models", [])),
                })
                continue

            try:
                response = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                payload = response.json()
                raw_models = payload.get("data", []) if isinstance(payload, dict) else []
                model_ids = []
                for item in raw_models:
                    if isinstance(item, dict):
                        model_id = item.get("id") or item.get("name")
                        if model_id:
                            model_ids.append(str(model_id))
                added = _merge_provider_models(provider, model_ids)
                updated.append({
                    "provider": provider.get("name"),
                    "status": "updated",
                    "added": added,
                    "total": len(provider.get("models", [])),
                })
            except Exception as e:
                updated.append({
                    "provider": provider.get("name"),
                    "status": "failed",
                    "reason": str(e),
                    "added": 0,
                    "total": len(provider.get("models", [])),
                })

    config["last_model_refresh_at"] = now_beijing().isoformat()
    save_llm_config(config)
    await log_operation(db, current_user, "更新模型列表", "model_provider", None, "全部模型厂商", detail="同步已配置厂商的模型列表")
    await db.commit()
    payload = await _enterprise_llm_payload(db, current_user)
    return {
        "ok": True,
        "updated": updated,
        **payload,
    }
