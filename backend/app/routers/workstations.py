import secrets
import socket
import string
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models import Agent, UserAccount, Workstation
from ..schemas import (
    WorkstationClientBindRequest,
    WorkstationClientBindResponse,
    WorkstationConnectivityRequest,
    WorkstationConnectivityResponse,
    WorkstationCreate,
    WorkstationResponse,
    WorkstationUpdate,
)
from ..time_utils import now_beijing
from .. import services

router = APIRouter(prefix="/api/workstations", tags=["workstations"])


def _bind_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _cloud_endpoint(host: str) -> tuple[str, int]:
    value = (host or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="云电脑需要填写公网地址")
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0]
    if ":" in value:
        host_part, port_part = value.rsplit(":", 1)
        try:
            return host_part.strip(), int(port_part)
        except ValueError:
            raise HTTPException(status_code=400, detail="云电脑端口格式不正确") from None
    return value, 3389


def _check_tcp_connectivity(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "ok"
    except OSError as e:
        return False, str(e)


async def _ensure_cloud_reachable(host: str) -> tuple[str, int]:
    target_host, target_port = _cloud_endpoint(host)
    ok, message = await asyncio.to_thread(_check_tcp_connectivity, target_host, target_port)
    if not ok:
        raise HTTPException(status_code=400, detail=f"云电脑连通性校验失败：无法连接 {target_host}:{target_port}，{message}")
    return target_host, target_port


async def _to_response(db: AsyncSession, workstation: Workstation) -> WorkstationResponse:
    assigned_count = (await db.execute(
        select(func.count(Agent.id)).where(Agent.workstation_id == workstation.id)
    )).scalar() or 0
    return WorkstationResponse(
        id=workstation.id,
        name=workstation.name,
        kind=workstation.kind,
        status=workstation.status,
        host=workstation.host,
        ip_address=workstation.ip_address,
        login_username=workstation.login_username,
        password_set=bool(workstation.login_password),
        client_version=workstation.client_version,
        bind_code=workstation.bind_code,
        notes=workstation.notes,
        assigned_agent_count=assigned_count,
        last_seen_at=workstation.last_seen_at,
        created_at=workstation.created_at,
        updated_at=workstation.updated_at,
    )


@router.get("", response_model=list[WorkstationResponse])
async def list_workstations(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    result = await db.execute(
        select(Workstation)
        .where(Workstation.enterprise_id == current_user.enterprise_id)
        .order_by(Workstation.kind.asc(), Workstation.created_at.desc())
    )
    return [await _to_response(db, item) for item in result.scalars().all()]


@router.post("/test-connectivity", response_model=WorkstationConnectivityResponse)
async def test_cloud_connectivity(
    data: WorkstationConnectivityRequest,
    current_user: UserAccount = Depends(require_admin),
):
    host, port = _cloud_endpoint(data.host)
    ok, message = await asyncio.to_thread(_check_tcp_connectivity, host, port)
    return WorkstationConnectivityResponse(ok=ok, host=host, port=port, message=message)


@router.post("", response_model=WorkstationResponse, status_code=201)
async def create_workstation(
    data: WorkstationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    status = data.status
    if data.kind == "local":
        status = "offline"
    else:
        await _ensure_cloud_reachable(data.host)
    workstation = Workstation(
        enterprise_id=current_user.enterprise_id,
        name=data.name,
        kind=data.kind,
        status=status,
        host=data.host if data.kind == "cloud" else "",
        ip_address="",
        login_username=data.login_username if data.kind == "cloud" else "",
        client_version=data.client_version if data.kind == "cloud" else "",
        bind_code=_bind_code(),
        notes=data.notes,
    )
    if data.kind == "cloud" and data.login_password:
        workstation.set_login_password(data.login_password)
    db.add(workstation)
    await db.flush()
    await services.log_operation(
        db,
        current_user,
        "新增工作电脑",
        "workstation",
        workstation.id,
        workstation.name,
        detail=f"类型：{'云电脑' if workstation.kind == 'cloud' else '本地客户端'}",
    )
    await db.commit()
    await db.refresh(workstation)
    return await _to_response(db, workstation)


@router.post("/{workstation_id}/bind-code", response_model=WorkstationResponse)
async def regenerate_bind_code(
    workstation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation or workstation.enterprise_id != current_user.enterprise_id:
        raise HTTPException(status_code=404, detail="Workstation not found")
    if workstation.kind != "local":
        raise HTTPException(status_code=400, detail="只有本地客户端电脑需要绑定码")
    workstation.bind_code = _bind_code()
    workstation.status = "offline"
    workstation.last_seen_at = None
    workstation.updated_at = now_beijing()
    await services.log_operation(db, current_user, "重新生成绑定码", "workstation", workstation.id, workstation.name, detail="本地客户端电脑绑定码已重新生成")
    await db.commit()
    await db.refresh(workstation)
    return await _to_response(db, workstation)


@router.post("/client/bind", response_model=WorkstationClientBindResponse)
async def bind_client_workstation(
    data: WorkstationClientBindRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workstation)
        .where(Workstation.bind_code == data.bind_code.strip().upper())
        .where(Workstation.kind == "local")
    )
    workstation = result.scalar_one_or_none()
    if not workstation:
        raise HTTPException(status_code=404, detail="绑定码不存在或已失效")

    workstation.name = data.machine_name.strip() or workstation.name
    workstation.ip_address = data.ip_address.strip()
    workstation.client_version = data.client_version.strip()
    if data.system_info:
        workstation.notes = (workstation.notes + "\n" if workstation.notes else "") + f"客户端上报：{data.system_info.strip()}"
    workstation.status = "online"
    workstation.last_seen_at = now_beijing()
    workstation.updated_at = now_beijing()
    await db.commit()
    return WorkstationClientBindResponse(
        workstation_id=workstation.id,
        name=workstation.name,
        enterprise_id=workstation.enterprise_id,
    )


@router.post("/client/heartbeat", response_model=WorkstationClientBindResponse)
async def heartbeat_client_workstation(
    data: WorkstationClientBindRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workstation)
        .where(Workstation.bind_code == data.bind_code.strip().upper())
        .where(Workstation.kind == "local")
    )
    workstation = result.scalar_one_or_none()
    if not workstation:
        raise HTTPException(status_code=404, detail="工作电脑未绑定")
    if data.machine_name.strip():
        workstation.name = data.machine_name.strip()
    if data.ip_address.strip():
        workstation.ip_address = data.ip_address.strip()
    if data.client_version.strip():
        workstation.client_version = data.client_version.strip()
    workstation.status = "online"
    workstation.last_seen_at = now_beijing()
    workstation.updated_at = now_beijing()
    await db.commit()
    return WorkstationClientBindResponse(
        workstation_id=workstation.id,
        name=workstation.name,
        enterprise_id=workstation.enterprise_id,
    )


@router.patch("/{workstation_id}", response_model=WorkstationResponse)
async def update_workstation(
    workstation_id: str,
    data: WorkstationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation or workstation.enterprise_id != current_user.enterprise_id:
        raise HTTPException(status_code=404, detail="Workstation not found")

    update_data = data.model_dump(exclude_unset=True)
    next_kind = update_data.get("kind", workstation.kind)
    next_host = update_data.get("host", workstation.host)
    if next_kind == "cloud" and any(key in update_data for key in {"kind", "host", "status"}):
        await _ensure_cloud_reachable(next_host)
    password_changed = "login_password" in update_data
    login_password = update_data.pop("login_password", None)
    for key, value in update_data.items():
        setattr(workstation, key, value)
    if password_changed and login_password is not None:
        workstation.set_login_password(login_password)
    workstation.updated_at = now_beijing()

    detail = services.describe_changed_fields(
        data.model_dump(exclude_unset=True),
        {
            "name": "电脑名称",
            "kind": "电脑类型",
            "status": "状态",
            "host": "公网地址",
            "login_username": "登录用户名",
            "login_password": "登录密码",
            "client_version": "客户端版本",
            "notes": "说明",
        },
    )
    await services.log_operation(db, current_user, "修改工作电脑", "workstation", workstation.id, workstation.name, detail=detail)
    await db.commit()
    await db.refresh(workstation)
    return await _to_response(db, workstation)


@router.delete("/{workstation_id}")
async def delete_workstation(
    workstation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation or workstation.enterprise_id != current_user.enterprise_id:
        raise HTTPException(status_code=404, detail="Workstation not found")
    assigned_count = (await db.execute(
        select(func.count(Agent.id)).where(Agent.workstation_id == workstation.id)
    )).scalar() or 0
    if assigned_count:
        raise HTTPException(status_code=409, detail="这台工作电脑已绑定 AI 员工，不能删除")

    target_name = workstation.name
    await db.delete(workstation)
    await services.log_operation(db, current_user, "删除工作电脑", "workstation", workstation_id, target_name, detail="删除未绑定的工作电脑")
    await db.commit()
    return {"ok": True}
