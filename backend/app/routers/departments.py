from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models import UserAccount
from ..schemas import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from .. import services

router = APIRouter(prefix="/api/departments", tags=["departments"])


async def _department_response(db: AsyncSession, department, enterprise_id: str) -> DepartmentResponse:
    counts = await services.get_department_member_counts(db, enterprise_id=enterprise_id)
    return DepartmentResponse(
        id=department.id,
        name=department.name,
        description=department.description,
        color=department.color,
        member_count=counts.get(department.name, 0),
        created_at=department.created_at,
        updated_at=department.updated_at,
    )


@router.get("", response_model=list[DepartmentResponse])
async def list_departments(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    departments = await services.get_departments(db, enterprise_id=current_user.enterprise_id)
    counts = await services.get_department_member_counts(db, enterprise_id=current_user.enterprise_id)
    return [
        DepartmentResponse(
            id=d.id,
            name=d.name,
            description=d.description,
            color=d.color,
            member_count=counts.get(d.name, 0),
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in departments
    ]


@router.post("", response_model=DepartmentResponse, status_code=201)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    try:
        department = await services.create_department(db, data, enterprise_id=current_user.enterprise_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await services.log_operation(db, current_user, "新增部门", "department", department.id, department.name)
    await db.commit()
    return await _department_response(db, department, current_user.enterprise_id)


@router.patch("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: str,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    try:
        department = await services.update_department(db, department_id, data, enterprise_id=current_user.enterprise_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    await services.log_operation(db, current_user, "修改部门", "department", department.id, department.name)
    await db.commit()
    return await _department_response(db, department, current_user.enterprise_id)


@router.delete("/{department_id}")
async def delete_department(
    department_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    try:
        department = await services.get_department(db, department_id, enterprise_id=current_user.enterprise_id)
        target_name = department.name if department else ""
        deleted = await services.delete_department(db, department_id, enterprise_id=current_user.enterprise_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="Department not found")
    await services.log_operation(db, current_user, "删除部门", "department", department_id, target_name)
    await db.commit()
    return {"ok": True}
