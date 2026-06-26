import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database import async_session
from .models import QueuedTask, QueuedTaskStatus
from .time_utils import now_beijing

logger = logging.getLogger(__name__)

# In-memory task queue
_in_memory_queue: asyncio.Queue = asyncio.Queue()
_worker_tasks: set = set()
_scheduled_task_processor: Optional[asyncio.Task] = None


async def update_task_status(
    task_id: str,
    status: QueuedTaskStatus,
    result: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> None:
    """Update queued task status in database."""
    async with async_session() as session:
        stmt = update(QueuedTask).where(QueuedTask.id == task_id).values(
            status=status.value,
            result=result,
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
            updated_at=now_beijing(),
        )
        await session.execute(stmt)
        await session.commit()


async def _execute_queued_task_wrapper(
    task_id: str,
    task_type: str,
    payload: Dict[str, Any],
) -> None:
    """Wrapper for executing queued tasks with error handling."""
    logger.info(f"Executing queued task {task_id} of type {task_type}")
    
    try:
        await update_task_status(
            task_id,
            QueuedTaskStatus.RUNNING,
            started_at=now_beijing(),
        )
        
        # Dispatch to appropriate handler based on task type
        result = await _handle_task(task_type, payload)
        
        await update_task_status(
            task_id,
            QueuedTaskStatus.COMPLETED,
            result=result,
            completed_at=now_beijing(),
        )
        
        logger.info(f"Task {task_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}", exc_info=True)
        await update_task_status(
            task_id,
            QueuedTaskStatus.FAILED,
            error_message=str(e),
            completed_at=now_beijing(),
        )


async def _handle_task(task_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle specific task types."""
    if task_type == "process_document":
        from .knowledge_service import process_document_task
        return await process_document_task(payload)
    elif task_type == "execute_workflow":
        from .workflow_service import execute_workflow_task
        return await execute_workflow_task(payload)
    else:
        raise ValueError(f"Unknown task type: {task_type}")


async def _worker() -> None:
    """Worker coroutine that processes tasks from the queue."""
    while True:
        try:
            task_id, task_type, payload = await _in_memory_queue.get()
            try:
                await _execute_queued_task_wrapper(task_id, task_type, payload)
            finally:
                _in_memory_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker error: {str(e)}", exc_info=True)


async def queue_task(
    enterprise_id: str,
    task_type: str,
    payload: Dict[str, Any],
    priority: int = 0,
    scheduled_at: Optional[datetime] = None,
) -> str:
    """Queue a new task."""
    async with async_session() as session:
        task = QueuedTask(
            enterprise_id=enterprise_id,
            task_type=task_type,
            payload=payload,
            status=QueuedTaskStatus.PENDING,
            priority=priority,
            scheduled_at=scheduled_at,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        
        # If not scheduled, queue immediately
        if not scheduled_at:
            await _in_memory_queue.put((task.id, task_type, payload))
            task.status = QueuedTaskStatus.QUEUED
            await session.commit()
        
        return task.id


async def scheduled_task_processor() -> None:
    """Process scheduled tasks periodically."""
    while True:
        try:
            async with async_session() as session:
                now = now_beijing()
                stmt = select(QueuedTask).where(
                    QueuedTask.status == QueuedTaskStatus.PENDING,
                    QueuedTask.scheduled_at <= now,
                ).order_by(QueuedTask.priority.desc(), QueuedTask.created_at)
                
                result = await session.execute(stmt)
                tasks = result.scalars().all()
                
                for task in tasks:
                    logger.info(f"Queuing scheduled task {task.id}")
                    await _in_memory_queue.put((task.id, task.task_type, task.payload))
                    task.status = QueuedTaskStatus.QUEUED
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"Scheduled task processor error: {str(e)}", exc_info=True)
        
        await asyncio.sleep(60)


async def start_task_queue() -> None:
    """Start the task queue system."""
    logger.info("Starting task queue system...")
    
    # Start worker tasks
    for _ in range(3):  # 3 workers
        task = asyncio.create_task(_worker())
        _worker_tasks.add(task)
        task.add_done_callback(_worker_tasks.discard)
    
    # Start scheduled task processor
    global _scheduled_task_processor
    _scheduled_task_processor = asyncio.create_task(scheduled_task_processor())
    
    logger.info("Task queue system started")


async def stop_task_queue() -> None:
    """Stop the task queue system."""
    logger.info("Stopping task queue system...")
    
    # Cancel workers
    for task in _worker_tasks:
        task.cancel()
    
    # Wait for workers to finish
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
    
    # Cancel scheduled task processor
    if _scheduled_task_processor:
        _scheduled_task_processor.cancel()
        try:
            await _scheduled_task_processor
        except asyncio.CancelledError:
            pass
    
    logger.info("Task queue system stopped")
