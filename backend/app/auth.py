import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_db
from .models import UserAccount

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, digest = stored.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
        return hmac.compare_digest(candidate.hex(), digest)
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def create_token(user: UserAccount) -> str:
    payload = {
        "sub": user.id,
        "enterprise_id": user.enterprise_id,
        "role": user.role,
        "agent_id": user.agent_id,
        "exp": int((datetime.utcnow() + timedelta(days=7)).timestamp()),
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = hmac.new(settings.secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(settings.secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64(expected), signature):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(datetime.utcnow().timestamp()):
            raise ValueError("expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录") from e


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    if not credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_token(credentials.credentials)
    result = await db.execute(select(UserAccount).where(UserAccount.id == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="账号不可用")
    return user


async def require_admin(user: UserAccount = Depends(get_current_user)) -> UserAccount:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="只有企业管理员可以执行该操作")
    return user


def ensure_agent_access(user: UserAccount, agent_id: str) -> None:
    if user.role == "admin":
        return
    if user.role == "employee" and user.agent_id == agent_id:
        return
    raise HTTPException(status_code=403, detail="无权访问该员工")
