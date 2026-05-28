from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import ensure_agent_access, get_current_user, require_admin
from ..database import get_db
from ..models import AgentRoutine, AgentIntegration
from ..models import UserAccount
from ..schemas import (
    AgentProfileResponse,
    AgentProfileUpdate,
    AgentRoutineCreate,
    AgentRoutineResponse,
    AgentRoutineUpdate,
    AgentIntegrationCreate,
    AgentIntegrationResponse,
    AgentIntegrationUpdate,
)
from .. import services

router = APIRouter(prefix="/api/agents", tags=["agent-memory"])


@router.get("/{agent_id}/profile", response_model=AgentProfileResponse)
async def get_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    agent = await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    profile = await services.get_agent_profile(db, agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentProfileResponse.model_validate(profile)


@router.put("/{agent_id}/profile", response_model=AgentProfileResponse)
async def update_profile(
    agent_id: str,
    data: AgentProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin),
):
    agent = await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    profile = await services.update_agent_profile(db, agent_id, data)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentProfileResponse.model_validate(profile)


@router.get("/{agent_id}/routines", response_model=list[AgentRoutineResponse])
async def list_routines(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    if not await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    routines = await services.get_agent_routines(db, agent_id)
    return [AgentRoutineResponse.model_validate(item) for item in routines]


@router.post("/{agent_id}/routines", response_model=AgentRoutineResponse, status_code=201)
async def create_routine(
    agent_id: str,
    data: AgentRoutineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    if not await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    routine = await services.create_agent_routine(db, agent_id, data)
    if not routine:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentRoutineResponse.model_validate(routine)


@router.patch("/{agent_id}/routines/{routine_id}", response_model=AgentRoutineResponse)
async def update_routine(
    agent_id: str,
    routine_id: str,
    data: AgentRoutineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    existing = await db.get(AgentRoutine, routine_id)
    if not existing or existing.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Routine not found")
    ensure_agent_access(current_user, agent_id)
    if not await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Routine not found")
    routine = await services.update_agent_routine(db, routine_id, data)
    if not routine:
        raise HTTPException(status_code=404, detail="Routine not found")
    return AgentRoutineResponse.model_validate(routine)


@router.delete("/{agent_id}/routines/{routine_id}")
async def delete_routine(
    agent_id: str,
    routine_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    routine = await db.get(AgentRoutine, routine_id)
    if not routine or routine.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Routine not found")
    ensure_agent_access(current_user, agent_id)
    if not await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Routine not found")
    await services.delete_agent_routine(db, routine_id)
    return {"ok": True}


@router.get("/{agent_id}/integrations", response_model=list[AgentIntegrationResponse])
async def list_integrations(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    if not await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    integrations = await services.get_agent_integrations(db, agent_id)
    return [AgentIntegrationResponse.model_validate(item) for item in integrations]


@router.post("/{agent_id}/integrations", response_model=AgentIntegrationResponse, status_code=201)
async def create_integration(
    agent_id: str,
    data: AgentIntegrationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    if not await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    integration = await services.create_agent_integration(db, agent_id, data)
    if not integration:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentIntegrationResponse.model_validate(integration)


@router.patch("/{agent_id}/integrations/{integration_id}", response_model=AgentIntegrationResponse)
async def update_integration(
    agent_id: str,
    integration_id: str,
    data: AgentIntegrationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    existing = await db.get(AgentIntegration, integration_id)
    if not existing or existing.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Integration not found")
    ensure_agent_access(current_user, agent_id)
    if not await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Integration not found")
    integration = await services.update_agent_integration(db, integration_id, data)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return AgentIntegrationResponse.model_validate(integration)


@router.delete("/{agent_id}/integrations/{integration_id}")
async def delete_integration(
    agent_id: str,
    integration_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    integration = await db.get(AgentIntegration, integration_id)
    if not integration or integration.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Integration not found")
    ensure_agent_access(current_user, agent_id)
    if not await services.get_agent(db, agent_id, enterprise_id=current_user.enterprise_id):
        raise HTTPException(status_code=404, detail="Integration not found")
    await services.delete_agent_integration(db, integration_id)
    return {"ok": True}
