from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import ensure_agent_access, get_current_user
from ..database import get_db
from ..models import UserAccount
from ..schemas import SmartTaskPlanResponse, SmartTaskRequest, TaskCreate, TaskResponse, TaskUpdate
from .. import services

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/{agent_id}/plan", response_model=SmartTaskPlanResponse)
async def plan_tasks(
    agent_id: str,
    data: SmartTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    try:
        plan = await services.plan_agent_tasks(
            db,
            agent_id,
            data.instruction,
            enterprise_id=current_user.enterprise_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return plan


@router.post("/{agent_id}", response_model=TaskResponse, status_code=201)
async def create_task(
    agent_id: str,
    data: TaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    agent = await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    task = await services.create_task(db, agent_id, data)
    if not task:
        raise HTTPException(status_code=404, detail="Agent not found")
    await services.log_operation(
        db,
        current_user,
        "新增任务" if current_user.role == "admin" else "AI员工新增任务",
        "task",
        task.id,
        task.title,
        detail=f"新增{ '定时任务' if task.task_type == 'scheduled' else '立即任务' }；执行员工：{agent.name}",
    )
    await db.commit()
    if task.task_type == "immediate":
        background_tasks.add_task(services.execute_task, task.id)
    return TaskResponse.model_validate(task)


@router.get("/agent/{agent_id}", response_model=list[TaskResponse])
async def list_tasks(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    agent = await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    tasks = await services.get_agent_tasks(db, agent_id)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    task = await services.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    ensure_agent_access(current_user, task.agent_id)
    agent = await services.get_agent(db, task.agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    existing = await services.get_task(db, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    ensure_agent_access(current_user, existing.agent_id)
    if not await services.get_agent(db, existing.agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Task not found")
    detail = services.describe_changed_fields(data.model_dump(exclude_unset=True), {
        "title": "标题",
        "description": "任务说明",
        "task_type": "任务类型",
        "schedule": "计划说明",
        "repeat": "重复规则",
        "priority": "优先级",
        "save_conversation": "保存对话设置",
        "next_run_at": "下次执行时间",
    })
    try:
        task = await services.update_task(db, task_id, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await services.log_operation(db, current_user, "修改任务", "task", task.id, task.title, detail=detail)
    await db.commit()
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    existing = await services.get_task(db, task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    ensure_agent_access(current_user, existing.agent_id)
    if not await services.get_agent(db, existing.agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Task not found")
    target_title = existing.title
    try:
        deleted = await services.delete_task(db, task_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    await services.log_operation(db, current_user, "删除任务", "task", task_id, target_title, detail="删除任务")
    await db.commit()
    return {"ok": True}
