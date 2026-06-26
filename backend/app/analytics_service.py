"""
Analytics service for collecting and retrieving platform usage statistics.
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from .models import (
    Conversation,
    Message,
    Task,
    Agent,
    OperationLog,
    UserAccount,
)
from .time_utils import now_beijing


class AnalyticsService:
    
    @staticmethod
    async def get_dashboard_stats(db: AsyncSession, enterprise_id: str) -> dict:
        """Get comprehensive dashboard statistics for an enterprise."""
        
        # 1. Agent statistics
        agent_result = await db.execute(
            select(
                func.count(Agent.id).label("total_agents"),
                func.count(case((Agent.status == "idle", 1))).label("idle_agents"),
                func.count(case((Agent.status == "working", 1))).label("working_agents"),
                func.count(case((Agent.status == "blocked", 1))).label("blocked_agents")
            ).where(Agent.enterprise_id == enterprise_id)
        )
        agent_stats = agent_result.first()._asdict()
        
        # 2. Task statistics
        now = now_beijing()
        task_result = await db.execute(
            select(
                func.count(Task.id).label("total_tasks"),
                func.count(case((Task.status == "pending", 1))).label("pending_tasks"),
                func.count(case((Task.status == "assigned", 1))).label("assigned_tasks"),
                func.count(case((Task.status == "running", 1))).label("running_tasks"),
                func.count(case((Task.status == "completed", 1))).label("completed_tasks"),
                func.count(case((Task.status == "failed", 1))).label("failed_tasks")
            ).where(
                and_(
                    Task.agent.has(enterprise_id=enterprise_id),
                    Task.created_at >= now - timedelta(days=7)
                )
            )
        )
        task_stats = task_result.first()._asdict()
        
        # 3. Conversation statistics
        conv_result = await db.execute(
            select(
                func.count(Conversation.id).label("total_conversations"),
                func.count(Message.id).label("total_messages")
            ).select_from(Conversation).outerjoin(
                Message, Conversation.id == Message.conversation_id
            ).where(Conversation.agent.has(enterprise_id=enterprise_id))
        )
        conv_stats = conv_result.first()._asdict()
        
        # 4. Recent activity (last 10 operations)
        recent_activities = await db.execute(
            select(
                OperationLog.action,
                OperationLog.target_type,
                OperationLog.target_name,
                OperationLog.detail,
                OperationLog.created_at,
                OperationLog.actor_username
            ).where(
                OperationLog.enterprise_id == enterprise_id
            ).order_by(
                OperationLog.created_at.desc()
            ).limit(10)
        )
        activities = []
        for row in recent_activities:
            activities.append({
                "action": row.action,
                "target_type": row.target_type,
                "target_name": row.target_name,
                "detail": row.detail,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "actor_username": row.actor_username
            })
        
        # 5. Daily activity for the last 7 days
        daily_stats = []
        for i in range(7):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            day_conv_result = await db.execute(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.agent.has(enterprise_id=enterprise_id),
                        Conversation.created_at >= day_start,
                        Conversation.created_at < day_end
                    )
                )
            )
            day_convs = day_conv_result.scalar()
            
            day_task_result = await db.execute(
                select(func.count(Task.id)).where(
                    and_(
                        Task.agent.has(enterprise_id=enterprise_id),
                        Task.created_at >= day_start,
                        Task.created_at < day_end
                    )
                )
            )
            day_tasks = day_task_result.scalar()
            
            daily_stats.append({
                "date": day_start.date().isoformat(),
                "conversations": day_convs or 0,
                "tasks": day_tasks or 0
            })
        
        return {
            "agents": agent_stats,
            "tasks": task_stats,
            "conversations": conv_stats,
            "recent_activities": activities,
            "daily_stats": list(reversed(daily_stats))
        }
