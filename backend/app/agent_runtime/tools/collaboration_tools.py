from datetime import datetime
from sqlalchemy import select

from ...database import async_session
from ...models import Agent, Task, TaskStatus
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
            query = select(Agent)
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
            source = await db.get(Agent, current_agent_id) if current_agent_id else None
            source_text = f"委派来源：{source.name}（{source.department or '未分配'} / {source.role}）\n\n" if source else ""

            task = Task(
                agent_id=target.id,
                title=title.strip()[:200],
                description=f"{source_text}{description.strip()}",
                status=TaskStatus.ASSIGNED.value,
                task_type="immediate",
                priority=priority if priority in {"low", "normal", "high"} else "normal",
                save_conversation=save_conversation,
                assigned_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)

            return ToolResult(
                success=True,
                data={
                    "message": "内部协作任务已创建",
                    "task_id": task.id,
                    "target_agent_id": target.id,
                    "target_agent_name": target.name,
                    "target_department": target.department,
                    "status": task.status,
                },
            )
