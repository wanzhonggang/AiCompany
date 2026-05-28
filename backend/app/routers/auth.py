from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_token, get_current_user, hash_password, verify_password
from ..database import get_db
from ..models import Enterprise, UserAccount
from ..schemas import AuthResponse, AuthUserResponse, EnterpriseRegisterRequest, LoginRequest, PasswordChangeRequest, PasswordUpdateResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _payment_quote(plan: str, billing_period: str, payment_method: str) -> dict:
    if plan == "trial":
        return {
            "amount": 0,
            "currency": "CNY",
            "method": payment_method,
            "summary": "体验版",
            "status": "trial",
        }
    monthly_price = 98
    amount = monthly_price if billing_period == "monthly" else int(monthly_price * 12 * 0.85)
    return {
        "amount": amount,
        "currency": "CNY",
        "method": payment_method,
        "summary": "正式版月付" if billing_period == "monthly" else "正式版年付（约 85 折）",
        "status": "pending_integration",
        "message": "微信/支付宝真实收款需要商户号和支付回调配置；当前接口先生成待支付订单信息。",
    }


def _user_response(user: UserAccount, enterprise: Enterprise) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        enterprise_id=user.enterprise_id,
        enterprise_name=enterprise.name,
        agent_id=user.agent_id,
        display_name=user.display_name or user.username,
    )


@router.post("/register-enterprise", response_model=AuthResponse)
async def register_enterprise(data: EnterpriseRegisterRequest, db: AsyncSession = Depends(get_db)):
    username = data.admin_username.strip().lower()
    existing = await db.execute(select(UserAccount).where(UserAccount.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="管理员账号已存在")

    now = datetime.utcnow()
    enterprise = Enterprise(
        name=data.enterprise_name.strip(),
        plan=data.plan,
        billing_period=data.billing_period,
        payment_status="trial" if data.plan == "trial" else "pending",
        expires_at=now + (timedelta(days=14) if data.plan == "trial" else timedelta(days=30 if data.billing_period == "monthly" else 365)),
        created_at=now,
        updated_at=now,
    )
    db.add(enterprise)
    await db.flush()

    user = UserAccount(
        enterprise_id=enterprise.id,
        username=username,
        password_hash=hash_password(data.admin_password),
        role="admin",
        display_name="企业管理员",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await db.refresh(enterprise)

    payment = _payment_quote(data.plan, data.billing_period, data.payment_method)
    return AuthResponse(
        token=create_token(user),
        user=_user_response(user, enterprise),
        payment_required=data.plan != "trial",
        payment=payment,
    )


@router.post("/login", response_model=AuthResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    username = data.username.strip().lower()
    result = await db.execute(select(UserAccount).where(UserAccount.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    if not user.enabled:
        raise HTTPException(status_code=403, detail="账号已停用")
    enterprise = await db.get(Enterprise, user.enterprise_id)
    if not enterprise:
        raise HTTPException(status_code=403, detail="企业不存在")
    return AuthResponse(token=create_token(user), user=_user_response(user, enterprise))


@router.get("/me", response_model=AuthUserResponse)
async def me(user: UserAccount = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    enterprise = await db.get(Enterprise, user.enterprise_id)
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    return _user_response(user, enterprise)


@router.patch("/password", response_model=PasswordUpdateResponse)
async def change_my_password(
    data: PasswordChangeRequest,
    user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not data.old_password or not verify_password(data.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    user.password_hash = hash_password(data.new_password)
    user.updated_at = datetime.utcnow()
    await db.commit()
    return PasswordUpdateResponse(username=user.username)
