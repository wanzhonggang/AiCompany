import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_admin, hash_password
from ..database import get_db
from ..models import AgentToolBinding, Enterprise, UserAccount
from ..schemas import AgentCreate, AgentUpdate, AgentResponse, StatsResponse, PasswordChangeRequest, PasswordUpdateResponse
from ..time_utils import now_beijing
from .. import services

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == "employee":
        return {"total": 1, "working": 0, "idle": 1, "blocked": 0, "completed": 0}
    return await services.get_agent_stats(db, enterprise_id=current_user.enterprise_id)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == "employee":
        if not current_user.agent_id:
            return []
        agent = await services.get_agent(db, current_user.agent_id, enterprise_id=current_user.enterprise_id)
        return [await _agent_to_response(db, agent)] if agent else []
    agents = await services.get_agents(db, enterprise_id=current_user.enterprise_id)
    return [
        await _agent_to_response(db, a)
        for a in agents
    ]


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    try:
        agent = await services.create_agent(db, data, enterprise_id=current_user.enterprise_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    enterprise = await db.get(Enterprise, current_user.enterprise_id)
    username = await _generate_employee_username(
        db,
        enterprise.name if enterprise else "企业",
        agent.department or "未分配",
    )
    init_password = _generate_temp_password()
    employee_user = UserAccount(
        enterprise_id=current_user.enterprise_id,
        username=username,
        password_hash=hash_password(init_password),
        role="employee",
        agent_id=agent.id,
        display_name=f"{agent.name}账号",
    )
    db.add(employee_user)
    await services.log_operation(
        db,
        current_user,
        "新增AI员工",
        "agent",
        agent.id,
        agent.name,
        detail=f"新增员工账号：{username}；模型：{agent.provider}/{agent.model_name}",
    )
    await db.commit()

    response = await _agent_to_response(db, agent)
    response.employee_username = username
    response.employee_init_password = init_password
    return response


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_detail(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == "employee" and current_user.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="无权访问该员工")
    agent = await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await _agent_to_response(db, agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    data: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    detail = services.describe_changed_fields(data.model_dump(exclude_unset=True), {
        "name": "姓名",
        "role": "职位",
        "department": "部门",
        "system_prompt": "系统提示词",
        "status": "状态",
        "skills": "技能",
        "avatar_color": "头像颜色",
        "provider": "模型厂商",
        "model_name": "模型",
        "max_iterations": "最大执行轮数",
    })
    try:
        agent = await services.update_agent(db, agent_id, data, enterprise_id=current_user.enterprise_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await services.log_operation(db, current_user, "修改AI员工", "agent", agent.id, agent.name, detail=detail)
    await db.commit()
    return await _agent_to_response(db, agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    agent = await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    target_name = agent.name if agent else ""
    deleted = await services.delete_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    await services.log_operation(db, current_user, "删除AI员工", "agent", agent_id, target_name, detail="删除员工及其绑定账号")
    await db.commit()


@router.patch("/{agent_id}/employee-password", response_model=PasswordUpdateResponse)
async def update_employee_password(
    agent_id: str,
    data: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    agent = await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await db.execute(
        select(UserAccount)
        .where(UserAccount.enterprise_id == current_user.enterprise_id)
        .where(UserAccount.agent_id == agent_id)
        .where(UserAccount.role == "employee")
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="员工账号不存在")
    employee.password_hash = hash_password(data.new_password)
    employee.updated_at = now_beijing()
    await services.log_operation(db, current_user, "修改员工密码", "agent", agent.id, agent.name, detail=f"更新登录密码；员工账号：{employee.username}")
    await db.commit()
    return PasswordUpdateResponse(username=employee.username)


async def _agent_to_response(db: AsyncSession, agent) -> AgentResponse:
    employee = await _get_employee_user(db, agent.id)
    tool_count = (await db.execute(
        select(func.count(AgentToolBinding.id)).where(AgentToolBinding.agent_id == agent.id)
    )).scalar() or 0
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        role=agent.role,
        department=agent.department,
        system_prompt=agent.system_prompt,
        status=agent.status,
        current_task=agent.current_task,
        skills=agent.skills,
        avatar_color=agent.avatar_color,
        provider=agent.provider,
        max_iterations=agent.max_iterations,
        model_name=agent.model_name,
        tool_count=tool_count,
        employee_username=employee.username if employee else None,
        employee_init_password=None,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def _generate_temp_password(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


async def _get_employee_user(db: AsyncSession, agent_id: str) -> UserAccount | None:
    result = await db.execute(
        select(UserAccount)
        .where(UserAccount.agent_id == agent_id)
        .where(UserAccount.role == "employee")
    )
    return result.scalar_one_or_none()


def _username_part(value: str) -> str:
    text = "".join(ch for ch in (value or "").strip().lower() if ch.isalnum() or ch in "-_")
    return text[:24] or "ai"


async def _generate_employee_username(db: AsyncSession, enterprise_name: str, department: str) -> str:
    base = f"{_username_part(enterprise_name)}-{_username_part(department)}-{_random_letters(3)}"
    counter = 1
    while True:
        username = f"{base}{counter}"
        existing = await db.execute(select(UserAccount).where(UserAccount.username == username))
        if not existing.scalar_one_or_none():
            return username
        counter += 1


def _random_letters(length: int) -> str:
    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(length))
