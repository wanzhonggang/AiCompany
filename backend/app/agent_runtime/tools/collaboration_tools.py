import asyncio
import re
from datetime import datetime, timedelta
from sqlalchemy import select

from ...database import async_session
from ...models import Agent, Task, TaskStatus
from ...time_utils import now_beijing, to_beijing_naive
from .base import BaseTool, ToolSpec, ToolResult


def _infer_next_run_at(text: str) -> datetime | None:
    now = now_beijing()
    hour = 9
    minute = 0

    match = re.search(r"(\d{1,2})[:：](\d{2})", text)
    if match:
        hour = max(0, min(23, int(match.group(1))))
        minute = max(0, min(59, int(match.group(2))))
    else:
        half_match = re.search(r"(上午|下午|晚上|今晚|中午)?\s*(\d{1,2})\s*点半", text)
        hour_match = half_match or re.search(r"(上午|下午|晚上|今晚|中午)?\s*(\d{1,2})\s*点", text)
        if not hour_match:
            if not re.search(r"(每天|每日|每周|每月|定时|明天)", text):
                return None
            hour = 9
            minute = 0
            period = ""
        else:
            hour = max(0, min(23, int(hour_match.group(2))))
            minute = 30 if half_match else 0
            period = hour_match.group(1) or ""
        if period in {"下午", "晚上", "今晚"} and hour < 12:
            hour += 12
        if period == "中午" and hour < 11:
            hour = 12

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "明天" in text:
        candidate += timedelta(days=1)
    elif candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _parse_next_run_at(value: str, fallback_text: str) -> datetime | None:
    if value:
        try:
            return to_beijing_naive(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except Exception:
            pass
    return _infer_next_run_at(fallback_text)


def _is_scheduled_text(text: str) -> bool:
    return bool(re.search(r"(每天|每日|每周|每月|定时|明天|上午|下午|晚上|今晚|中午|\d{1,2}[:：]\d{2}|\d{1,2}\s*点)", text))


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
                    "task_type": {
                        "type": "string",
                        "description": "Task type for the target employee: immediate or scheduled. Use scheduled when the user gives a future time or recurring schedule.",
                        "default": "immediate",
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Human-readable schedule, such as 今天10:30, 明天上午9点, 每天18:00.",
                    },
                    "repeat": {
                        "type": "string",
                        "description": "Repeat rule: none, daily, or weekly.",
                        "default": "none",
                    },
                    "next_run_at": {
                        "type": "string",
                        "description": "Optional ISO datetime for first execution in Beijing time.",
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
        task_type: str = "immediate",
        schedule: str = "",
        repeat: str = "none",
        next_run_at: str = "",
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

            def score(agent: Agent) -> int:
                value = 0
                name = (agent.name or "").lower()
                role = (agent.role or "").lower()
                department = (agent.department or "").lower()
                if keyword:
                    if keyword in name:
                        value += 100
                    if keyword in role:
                        value += 80
                    if keyword in department:
                        value += 50
                if dept and dept in department:
                    value += 60
                return value

            candidates = [
                agent for agent in agents
                if agent.id != source.id
                and (not dept or dept in (agent.department or "").lower())
                and (not keyword or score(agent) > 0)
            ]
            candidates.sort(key=score, reverse=True)
            if not candidates:
                return ToolResult(
                    success=False,
                    error=f"未找到目标员工：{target_agent_name} {target_department}".strip(),
                )

            target = candidates[0]
            source_text = f"委派来源：{source.name}（{source.department or '未分配'} / {source.role}）\n\n" if source else ""
            full_text = f"{title}\n{description}\n{schedule}"
            normalized_repeat = repeat if repeat in {"none", "daily", "weekly"} else "none"
            inferred_scheduled = _is_scheduled_text(full_text) or normalized_repeat != "none"
            normalized_task_type = "scheduled" if task_type == "scheduled" or inferred_scheduled else "immediate"
            normalized_next_run_at = _parse_next_run_at(next_run_at, full_text) if normalized_task_type == "scheduled" else None

            task = Task(
                agent_id=target.id,
                title=title.strip()[:200],
                description=f"{source_text}{description.strip()}",
                status=TaskStatus.ASSIGNED.value,
                task_type=normalized_task_type,
                schedule=schedule.strip() or ("由委派指令推断执行时间" if normalized_task_type == "scheduled" else None),
                repeat=normalized_repeat if normalized_task_type == "scheduled" else "none",
                priority=priority if priority in {"low", "normal", "high"} else "normal",
                save_conversation=save_conversation,
                next_run_at=normalized_next_run_at,
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
                detail=f"{source.name} 委派给 {target.name}；类型：{normalized_task_type}",
                enterprise_id=source.enterprise_id,
                actor_agent_id=source.id,
                actor_agent_name=source.name,
            )
            await db.commit()
            await db.refresh(task)

            from ...services import execute_task
            if task.task_type == "immediate":
                asyncio.create_task(execute_task(task.id))

            return ToolResult(
                success=True,
                data={
                    "message": "内部协作任务已创建" + ("并开始执行" if task.task_type == "immediate" else "，将按计划执行"),
                    "task_id": task.id,
                    "target_agent_id": target.id,
                    "target_agent_name": target.name,
                    "target_department": target.department,
                    "status": task.status,
                    "task_type": task.task_type,
                    "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                },
            )
