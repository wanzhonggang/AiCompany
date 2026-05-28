from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import hash_password, require_admin
from ..database import get_db
from ..models import UserAccount
from ..schemas import AdminCreateRequest, AdminResponse
from ..time_utils import now_beijing

router = APIRouter(prefix="/api/admins", tags=["admins"])


@router.get("", response_model=list[AdminResponse])
async def list_admins(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    result = await db.execute(
        select(UserAccount)
        .where(UserAccount.enterprise_id == current_user.enterprise_id)
        .where(UserAccount.role == "admin")
        .order_by(UserAccount.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=AdminResponse, status_code=201)
async def create_admin(
    data: AdminCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    username = data.username.strip().lower()
    existing = await db.execute(select(UserAccount).where(UserAccount.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="管理员账号已存在")

    admin = UserAccount(
        enterprise_id=current_user.enterprise_id,
        username=username,
        password_hash=hash_password(data.password),
        role="admin",
        display_name=data.display_name.strip() or "企业管理员",
        enabled=True,
        created_at=now_beijing(),
        updated_at=now_beijing(),
    )
    db.add(admin)
    await db.flush()
    await db.commit()
    await db.refresh(admin)
    return admin
