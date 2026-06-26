"""
Analytics API router for usage statistics and dashboards.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..auth import get_current_user
from ..analytics_service import AnalyticsService
from ..models import UserAccount

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    """Get dashboard statistics for the current enterprise."""
    enterprise_id = current_user.enterprise_id
    stats = await AnalyticsService.get_dashboard_stats(db, enterprise_id)
    return stats
