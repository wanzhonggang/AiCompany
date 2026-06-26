from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..auth import get_current_user
from ..database import get_db
from ..schemas import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowStepResponse,
    WorkflowExecutionCreate,
    WorkflowExecutionResponse,
)
from ..models import UserAccount
from ..workflow_service import (
    create_workflow,
    get_workflows,
    get_workflow,
    create_workflow_execution,
    get_workflow_executions,
)
from ..task_queue import queue_task

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _status_value(status) -> str:
    return getattr(status, "value", status)


@router.post("", response_model=WorkflowResponse)
async def create_wf(
    data: WorkflowCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow."""
    workflow = await create_workflow(
        db,
        current_user.enterprise_id,
        data.name,
        data.description,
        data.enabled,
        [s.model_dump() for s in data.steps] if data.steps else None,
    )
    return WorkflowResponse(
        id=workflow.id,
        enterprise_id=workflow.enterprise_id,
        name=workflow.name,
        description=workflow.description,
        enabled=workflow.enabled,
        steps=[
            WorkflowStepResponse(
                id=step.id,
                workflow_id=step.workflow_id,
                name=step.name,
                step_type=step.step_type,
                order=step.order,
                config=step.config,
                created_at=step.created_at,
                updated_at=step.updated_at,
            )
            for step in workflow.steps
        ],
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


@router.get("", response_model=List[WorkflowResponse])
async def list_wfs(
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all workflows."""
    workflows = await get_workflows(db, current_user.enterprise_id)
    return [
        WorkflowResponse(
            id=wf.id,
            enterprise_id=wf.enterprise_id,
            name=wf.name,
            description=wf.description,
            enabled=wf.enabled,
            steps=[
                WorkflowStepResponse(
                    id=step.id,
                    workflow_id=step.workflow_id,
                    name=step.name,
                    step_type=step.step_type,
                    order=step.order,
                    config=step.config,
                    created_at=step.created_at,
                    updated_at=step.updated_at,
                )
                for step in wf.steps
            ],
            created_at=wf.created_at,
            updated_at=wf.updated_at,
        )
        for wf in workflows
    ]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_wf(
    workflow_id: str,
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a workflow by ID."""
    workflow = await get_workflow(db, workflow_id, current_user.enterprise_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(
        id=workflow.id,
        enterprise_id=workflow.enterprise_id,
        name=workflow.name,
        description=workflow.description,
        enabled=workflow.enabled,
        steps=[
            WorkflowStepResponse(
                id=step.id,
                workflow_id=step.workflow_id,
                name=step.name,
                step_type=step.step_type,
                order=step.order,
                config=step.config,
                created_at=step.created_at,
                updated_at=step.updated_at,
            )
            for step in workflow.steps
        ],
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


@router.post("/{workflow_id}/executions", response_model=WorkflowExecutionResponse)
async def execute_wf(
    workflow_id: str,
    data: WorkflowExecutionCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a workflow."""
    try:
        execution = await create_workflow_execution(
            db,
            workflow_id,
            data.input_data,
            current_user.enterprise_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    
    # Queue workflow execution
    await queue_task(
        current_user.enterprise_id,
        "execute_workflow",
        {"execution_id": execution.id},
    )
    
    return WorkflowExecutionResponse(
        id=execution.id,
        workflow_id=execution.workflow_id,
        status=_status_value(execution.status),
        input_data=execution.input_data,
        output_data=execution.output_data,
        error_message=execution.error_message,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        created_at=execution.created_at,
    )


@router.get("/{workflow_id}/executions", response_model=List[WorkflowExecutionResponse])
async def list_executions(
    workflow_id: str,
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List workflow executions."""
    try:
        executions = await get_workflow_executions(db, workflow_id, current_user.enterprise_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return [
        WorkflowExecutionResponse(
            id=exec.id,
            workflow_id=exec.workflow_id,
            status=_status_value(exec.status),
            input_data=exec.input_data,
            output_data=exec.output_data,
            error_message=exec.error_message,
            started_at=exec.started_at,
            completed_at=exec.completed_at,
            created_at=exec.created_at,
        )
        for exec in executions
    ]
