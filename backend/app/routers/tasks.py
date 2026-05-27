from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import TaskCreate, TaskResponse, TaskUpdate
from .. import services

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/{agent_id}", response_model=TaskResponse, status_code=201)
async def create_task(
    agent_id: str,
    data: TaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    task = await services.create_task(db, agent_id, data)
    if not task:
        raise HTTPException(status_code=404, detail="Agent not found")
    if task.task_type == "immediate":
        background_tasks.add_task(services.execute_task, task.id)
    return TaskResponse.model_validate(task)


@router.get("/agent/{agent_id}", response_model=list[TaskResponse])
async def list_tasks(agent_id: str, db: AsyncSession = Depends(get_db)):
    tasks = await services.get_agent_tasks(db, agent_id)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await services.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, data: TaskUpdate, db: AsyncSession = Depends(get_db)):
    try:
        task = await services.update_task(db, task_id, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    try:
        deleted = await services.delete_task(db, task_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
