import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (
    Workflow,
    WorkflowStep,
    WorkflowExecution,
    WorkflowStepExecution,
    WorkflowExecutionStatus,
    WorkflowStepType,
)
from .time_utils import now_beijing
from .database import async_session

logger = logging.getLogger(__name__)


async def create_workflow(
    session: AsyncSession,
    enterprise_id: str,
    name: str,
    description: str = "",
    enabled: bool = True,
    steps: Optional[List[Dict[str, Any]]] = None,
) -> Workflow:
    """Create a new workflow."""
    workflow = Workflow(
        enterprise_id=enterprise_id,
        name=name,
        description=description,
        enabled=enabled,
    )
    session.add(workflow)
    await session.flush()
    
    if steps:
        for step_data in steps:
            step = WorkflowStep(
                workflow_id=workflow.id,
                name=step_data["name"],
                step_type=step_data["step_type"],
                order=step_data["order"],
                config=step_data.get("config", {}),
            )
            session.add(step)
    
    await session.commit()
    await session.refresh(workflow)
    return workflow


async def get_workflows(
    session: AsyncSession,
    enterprise_id: str,
) -> List[Workflow]:
    """Get all workflows for an enterprise."""
    stmt = select(Workflow).where(Workflow.enterprise_id == enterprise_id).options(
        selectinload(Workflow.steps)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_workflow(
    session: AsyncSession,
    workflow_id: str,
    enterprise_id: str,
) -> Optional[Workflow]:
    """Get a workflow by ID."""
    stmt = select(Workflow).where(
        Workflow.id == workflow_id,
        Workflow.enterprise_id == enterprise_id,
    ).options(selectinload(Workflow.steps))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_workflow_execution(
    session: AsyncSession,
    workflow_id: str,
    input_data: Dict[str, Any],
    enterprise_id: str,
) -> WorkflowExecution:
    """Create a new workflow execution."""
    workflow = await get_workflow(session, workflow_id, enterprise_id)
    if not workflow:
        raise ValueError("Workflow not found")
    
    execution = WorkflowExecution(
        workflow_id=workflow_id,
        status=WorkflowExecutionStatus.PENDING.value,
        input_data=input_data,
    )
    session.add(execution)
    await session.commit()
    await session.refresh(execution)
    
    return execution


async def execute_workflow_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a workflow task for the queue."""
    execution_id = payload["execution_id"]
    
    async with async_session() as session:
        stmt = select(WorkflowExecution).where(WorkflowExecution.id == execution_id).options(
            selectinload(WorkflowExecution.workflow).selectinload(Workflow.steps)
        )
        result = await session.execute(stmt)
        execution = result.scalar_one_or_none()
        
        if not execution:
            raise ValueError("Workflow execution not found")
        
        execution.status = WorkflowExecutionStatus.RUNNING.value
        execution.started_at = now_beijing()
        await session.commit()
        
        try:
            # Sort steps by order
            steps = sorted(execution.workflow.steps, key=lambda s: s.order)
            
            context = execution.input_data.copy()
            
            for step in steps:
                # Create step execution
                step_exec = WorkflowStepExecution(
                    execution_id=execution.id,
                    step_id=step.id,
                    status=WorkflowExecutionStatus.RUNNING.value,
                    input_data=context.copy(),
                    started_at=now_beijing(),
                )
                session.add(step_exec)
                await session.flush()
                
                try:
                    # Execute step based on type
                    step_result = await _execute_step(step, context)
                    context.update(step_result)
                    
                    step_exec.status = WorkflowExecutionStatus.COMPLETED.value
                    step_exec.output_data = step_result
                    step_exec.completed_at = now_beijing()
                    
                except Exception as e:
                    logger.error(f"Step {step.id} failed: {str(e)}", exc_info=True)
                    step_exec.status = WorkflowExecutionStatus.FAILED.value
                    step_exec.error_message = str(e)
                    step_exec.completed_at = now_beijing()
                    await session.commit()
                    raise
            
            execution.status = WorkflowExecutionStatus.COMPLETED.value
            execution.output_data = context
            execution.completed_at = now_beijing()
            await session.commit()
            
            return {
                "execution_id": execution.id,
                "output_data": context,
            }
            
        except Exception as e:
            execution.status = WorkflowExecutionStatus.FAILED.value
            execution.error_message = str(e)
            execution.completed_at = now_beijing()
            await session.commit()
            raise


async def _execute_step(
    step: WorkflowStep,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a single workflow step."""
    step_type = WorkflowStepType(step.step_type)
    config = step.config
    
    if step_type == WorkflowStepType.LLM:
        return await _execute_llm_step(config, context)
    elif step_type == WorkflowStepType.TOOL:
        return await _execute_tool_step(config, context)
    elif step_type == WorkflowStepType.CONDITION:
        return await _execute_condition_step(config, context)
    elif step_type == WorkflowStepType.WAIT:
        return await _execute_wait_step(config, context)
    elif step_type == WorkflowStepType.KNOWLEDGE_RETRIEVAL:
        return await _execute_knowledge_step(config, context)
    else:
        raise ValueError(f"Unsupported step type: {step_type}")


async def _execute_llm_step(
    config: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute an LLM step (placeholder)."""
    # In a real implementation, you would call your LLM provider here
    prompt = config.get("prompt", "")
    # Format prompt with context variables
    formatted_prompt = prompt.format(**context)
    
    return {
        "llm_response": f"LLM response to: {formatted_prompt[:50]}...",
    }


async def _execute_tool_step(
    config: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a tool step (placeholder)."""
    tool_name = config.get("tool_name", "")
    tool_params = config.get("params", {})
    
    # Format parameters with context
    formatted_params = {
        k: v.format(**context) if isinstance(v, str) else v
        for k, v in tool_params.items()
    }
    
    return {
        "tool_result": f"Executed tool {tool_name} with params: {formatted_params}",
    }


async def _execute_condition_step(
    config: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a condition step (placeholder)."""
    condition = config.get("condition", "")
    # Simple condition evaluation (in production, use a safer evaluator)
    try:
        result = eval(condition, {}, context)
    except:
        result = False
    
    return {
        "condition_met": bool(result),
    }


async def _execute_wait_step(
    config: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a wait step."""
    import asyncio
    wait_seconds = config.get("seconds", 1)
    await asyncio.sleep(wait_seconds)
    
    return {
        "waited_seconds": wait_seconds,
    }


async def _execute_knowledge_step(
    config: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a knowledge retrieval step (placeholder)."""
    query = config.get("query", "")
    formatted_query = query.format(**context)
    
    return {
        "knowledge_results": [],
        "query_used": formatted_query,
    }


async def get_workflow_executions(
    session: AsyncSession,
    workflow_id: str,
    enterprise_id: str,
) -> List[WorkflowExecution]:
    """Get all executions for a workflow."""
    workflow = await get_workflow(session, workflow_id, enterprise_id)
    if not workflow:
        raise ValueError("Workflow not found")
    
    stmt = select(WorkflowExecution).where(
        WorkflowExecution.workflow_id == workflow_id
    ).order_by(WorkflowExecution.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())
