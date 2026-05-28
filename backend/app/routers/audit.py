from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models import OperationLog, UserAccount
from ..schemas import OperationLogResponse

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs", response_model=list[OperationLogResponse])
async def list_operation_logs(
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    capped_limit = min(max(limit, 1), 500)
    result = await db.execute(
        select(OperationLog)
        .where(OperationLog.enterprise_id == current_user.enterprise_id)
        .order_by(OperationLog.created_at.desc())
        .limit(capped_limit)
    )
    return list(result.scalars().all())
