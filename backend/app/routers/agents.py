from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import AgentCreate, AgentUpdate, AgentResponse, StatsResponse
from .. import services

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    return await services.get_agent_stats(db)


@router.get("", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    agents = await services.get_agents(db)
    return [
        AgentResponse(
            id=a.id,
            name=a.name,
            role=a.role,
            department=a.department,
            system_prompt=a.system_prompt,
            status=a.status,
            current_task=a.current_task,
            skills=a.skills,
            avatar_color=a.avatar_color,
            provider=a.provider,
            max_iterations=a.max_iterations,
            model_name=a.model_name,
            tool_count=len(a.tool_bindings),
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in agents
    ]


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(data: AgentCreate, db: AsyncSession = Depends(get_db)):
    agent = await services.create_agent(db, data)
    return _agent_to_response(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_detail(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await services.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_response(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, data: AgentUpdate, db: AsyncSession = Depends(get_db)):
    agent = await services.update_agent(db, agent_id, data)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_response(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await services.delete_agent(db, agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")


def _agent_to_response(agent) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        role=agent.role,
        department=agent.department,
        system_prompt=agent.system_prompt,
        status=agent.status,
        current_task=agent.current_task,
        skills=agent.skills,
        avatar_color=agent.avatar_color,
        provider=agent.provider,
        max_iterations=agent.max_iterations,
        model_name=agent.model_name,
        tool_count=len(agent.tool_bindings),
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )
