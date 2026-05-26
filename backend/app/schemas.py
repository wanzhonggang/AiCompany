from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ---- Agent ----
class AgentCreate(BaseModel):
    name: str = Field(..., max_length=100)
    role: str = Field(..., max_length=100)
    department: str = ""
    system_prompt: str = ""
    skills: List[str] = Field(default_factory=list)
    avatar_color: str = "#06b6d4"
    provider: str = "deepseek"
    max_iterations: int = 25
    model_name: str = "deepseek-chat"


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    system_prompt: Optional[str] = None
    status: Optional[str] = None
    skills: Optional[List[str]] = None
    avatar_color: Optional[str] = None
    provider: Optional[str] = None
    max_iterations: Optional[int] = None
    model_name: Optional[str] = None


class AgentResponse(BaseModel):
    id: str
    name: str
    role: str
    department: str
    system_prompt: str
    status: str
    current_task: Optional[str]
    skills: List[str]
    avatar_color: str
    provider: str
    max_iterations: int
    model_name: str
    tool_count: int = 0
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---- Chat ----
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    tool_calls: Optional[list] = None


# ---- Task ----
class TaskCreate(BaseModel):
    title: str = Field(..., max_length=200)
    description: str = ""
    priority: str = "normal"


class TaskResponse(BaseModel):
    id: str
    agent_id: str
    title: str
    description: str
    status: str
    priority: str
    output: Optional[str]
    error: Optional[str]
    iterations: int
    tokens_used: int
    assigned_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---- Stats ----
class StatsResponse(BaseModel):
    total: int
    working: int
    idle: int
    blocked: int
    completed: int
