import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_providers_safe, load_llm_config
from .database import init_db, async_session
from .routers import agents, chat, tools, tasks
from .models import Agent, AgentToolBinding, ToolDefinition
from .services import BUILTIN_TOOLS, execute_task, get_due_scheduled_tasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await seed_data()
    scheduler_task = asyncio.create_task(scheduled_task_loop())
    logger.info("AI Employee Platform started")
    try:
        yield
    finally:
        scheduler_task.cancel()
    # Shutdown


async def scheduled_task_loop():
    while True:
        try:
            async with async_session() as db:
                due_tasks = await get_due_scheduled_tasks(db)
            for task in due_tasks:
                asyncio.create_task(execute_task(task.id))
        except Exception as e:
            logger.warning("Scheduled task loop failed: %s", e)
        await asyncio.sleep(30)


async def seed_data():
    """Seed initial agents and keep builtin tool bindings in sync."""
    async with async_session() as db:
        from sqlalchemy import select, func

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
                db.add(Agent(**ad))
            await db.flush()

        agents = (await db.execute(select(Agent))).scalars().all()
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "name": "AI Employee Platform"}


@app.get("/api/llm/providers")
async def list_providers():
    """Return available LLM providers and models (API keys redacted)."""
    config = load_llm_config()
    return {
        "providers": get_providers_safe(),
        "default_provider": config.get("default_provider", ""),
        "default_model": config.get("default_model", ""),
    }
