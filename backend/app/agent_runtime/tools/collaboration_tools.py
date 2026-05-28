import asyncio
from sqlalchemy import select

from ...database import async_session
from ...models import Agent, Task, TaskStatus
from ...time_utils import now_beijing
from .base import BaseTool, ToolSpec, ToolResult


class DelegateTaskTool(BaseTool):
    name = "delegate_task"
    category = "collaboration"
    description = (
        "Create an internal task for another AI employee in this platform. "
        "Use this when the user asks to notify, coordinate with, hand off to, or ask another employee/department to do work. "
        "This does not require SMTP email."
    )
    timeout_seconds = 30

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "target_agent_name": {
                        "type": "string",
                        "description": "Name or partial name of the AI employee who should receive the task.",
                    },
                    "target_department": {
                        "type": "string",
                        "description": "Optional department name to help find the target employee.",
                    },
                    "title": {"type": "string", "description": "Task title for the target employee."},
                    "description": {
                        "type": "string",
                        "description": "Detailed instructions, context, expected output, and deadline if any.",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Task priority: low, normal, or high. Defaults to normal.",
                    },
                    "save_conversation": {
                        "type": "boolean",
                        "description": "Whether to create a saved conversation for this delegated task. Defaults to true.",
                    },
                },
                "required": ["target_agent_name", "title", "description"],
            },
        )

    async def execute(
        self,
        target_agent_name: str = "",
        target_department: str = "",
        title: str = "",
        description: str = "",
        priority: str = "normal",
        save_conversation: bool = True,
        current_agent_id: str = "",
        **kwargs,
    ) -> ToolResult:
        if not target_agent_name.strip():
            return ToolResult(success=False, error="target_agent_name is required")
        if not title.strip():
            return ToolResult(success=False, error="title is required")

        async with async_session() as db:
            source = await db.get(Agent, current_agent_id) if current_agent_id else None
            if not source:
                return ToolResult(success=False, error="无法确认当前员工身份，不能委派任务")

            query = select(Agent).where(Agent.enterprise_id == source.enterprise_id)
            agents = list((await db.execute(query)).scalars().all())
            keyword = target_agent_name.strip().lower()
            dept = target_department.strip().lower()

            candidates = [
                agent for agent in agents
                if keyword in agent.name.lower()
                and (not dept or dept in (agent.department or "").lower())
            ]
            if not candidates:
                return ToolResult(
                    success=False,
                    error=f"未找到目标员工：{target_agent_name} {target_department}".strip(),
                )

            target = candidates[0]
            source_text = f"委派来源：{source.name}（{source.department or '未分配'} / {source.role}）\n\n" if source else ""

            task = Task(
                agent_id=target.id,
                title=title.strip()[:200],
                description=f"{source_text}{description.strip()}",
                status=TaskStatus.ASSIGNED.value,
                task_type="immediate",
                priority=priority if priority in {"low", "normal", "high"} else "normal",
                save_conversation=save_conversation,
                assigned_at=now_beijing(),
                created_at=now_beijing(),
            )
            db.add(task)
            await db.flush()
            from ...services import log_operation
            await log_operation(
                db,
                None,
                "AI员工新增任务",
                "task",
                task.id,
                task.title,
                detail=f"{source.name} 委派给 {target.name}",
                enterprise_id=source.enterprise_id,
                actor_agent_id=source.id,
                actor_agent_name=source.name,
            )
            await db.commit()
            await db.refresh(task)

            from ...services import execute_task
            asyncio.create_task(execute_task(task.id))

            return ToolResult(
                success=True,
                data={
                    "message": "内部协作任务已创建并开始执行",
                    "task_id": task.id,
                    "target_agent_id": target.id,
                    "target_agent_name": target.name,
                    "target_department": target.department,
                    "status": task.status,
                },
            )
