from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from .. import services

router = APIRouter(prefix="/api/departments", tags=["departments"])


async def _department_response(db: AsyncSession, department) -> DepartmentResponse:
    counts = await services.get_department_member_counts(db)
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
async def list_departments(db: AsyncSession = Depends(get_db)):
    departments = await services.get_departments(db)
    counts = await services.get_department_member_counts(db)
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
async def create_department(data: DepartmentCreate, db: AsyncSession = Depends(get_db)):
    try:
        department = await services.create_department(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await _department_response(db, department)


@router.patch("/{department_id}", response_model=DepartmentResponse)
async def update_department(department_id: str, data: DepartmentUpdate, db: AsyncSession = Depends(get_db)):
    try:
        department = await services.update_department(db, department_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    return await _department_response(db, department)


@router.delete("/{department_id}")
async def delete_department(department_id: str, db: AsyncSession = Depends(get_db)):
    try:
        deleted = await services.delete_department(db, department_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not deleted:
        raise HTTPException(status_code=404, detail="Department not found")
    return {"ok": True}
