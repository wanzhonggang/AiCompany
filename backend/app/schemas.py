from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ---- Agent ----
class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., min_length=1, max_length=100)
    department: str = Field(default="", max_length=100)
    system_prompt: str = Field(default="", max_length=8000)
    skills: List[str] = Field(default_factory=list)
    avatar_color: str = "#06b6d4"
    provider: str = Field(default="deepseek", max_length=50)
    max_iterations: int = Field(default=25, ge=1, le=100)
    model_name: str = Field(default="", max_length=100)


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    role: Optional[str] = Field(default=None, min_length=1, max_length=100)
    department: Optional[str] = Field(default=None, max_length=100)
    system_prompt: Optional[str] = Field(default=None, max_length=8000)
    status: Optional[str] = Field(default=None, max_length=20)
    skills: Optional[List[str]] = None
    avatar_color: Optional[str] = Field(default=None, max_length=7)
    provider: Optional[str] = Field(default=None, max_length=50)
    max_iterations: Optional[int] = Field(default=None, ge=1, le=100)
    model_name: Optional[str] = Field(default=None, max_length=100)


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
    message: str = Field(..., min_length=1, max_length=20000)
    conversation_id: Optional[str] = None
    save_conversation: bool = True


class ConversationRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    tool_calls: Optional[list] = None


# ---- Task ----
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    task_type: str = Field(default="immediate", pattern="^(immediate|scheduled)$")
    schedule: Optional[str] = Field(default=None, max_length=200)
    repeat: str = Field(default="none", pattern="^(none|daily|weekly)$")
    priority: str = Field(default="normal", max_length=10)
    save_conversation: bool = True
    next_run_at: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: str
    agent_id: str
    conversation_id: Optional[str]
    title: str
    description: str
    status: str
    task_type: str
    schedule: Optional[str]
    repeat: str
    priority: str
    save_conversation: bool
    output: Optional[str]
    error: Optional[str]
    iterations: int
    tokens_used: int
    created_at: Optional[datetime]
    assigned_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---- Stats ----
class StatsResponse(BaseModel):
    total: int
    working: int
    idle: int
    blocked: int
    completed: int
