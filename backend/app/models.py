import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Boolean, Integer, Enum as SAEnum
from sqlalchemy.orm import relationship
from .database import Base
import enum


def gen_id():
    return uuid.uuid4().hex[:12]


class AgentStatus(str, enum.Enum):
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(12), primary_key=True, default=gen_id)
    name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)
    department = Column(String(100), default="")
    system_prompt = Column(Text, default="")
    status = Column(String(20), default=AgentStatus.IDLE.value)
    current_task = Column(String(200), nullable=True)
    skills = Column(JSON, default=list)
    avatar_color = Column(String(7), default="#06b6d4")
    provider = Column(String(50), default="deepseek")
    max_iterations = Column(Integer, default=25)
    model_name = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks = relationship("Task", back_populates="agent", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="agent", cascade="all, delete-orphan")
    tool_bindings = relationship("AgentToolBinding", back_populates="agent", cascade="all, delete-orphan")


class Department(Base):
    __tablename__ = "departments"

    id = Column(String(12), primary_key=True, default=gen_id)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, default="")
    color = Column(String(7), default="#06b6d4")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"

    id = Column(String(12), primary_key=True, default=gen_id)
    name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    category = Column(String(50), default="general")
    is_builtin = Column(Boolean, default=True)


class AgentToolBinding(Base):
    __tablename__ = "agent_tool_bindings"

    id = Column(String(12), primary_key=True, default=gen_id)
    agent_id = Column(String(12), ForeignKey("agents.id"), nullable=False)
    tool_name = Column(String(50), nullable=False)
    enabled = Column(Boolean, default=True)

    agent = relationship("Agent", back_populates="tool_bindings")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(12), primary_key=True, default=gen_id)
    agent_id = Column(String(12), ForeignKey("agents.id"), nullable=False)
    conversation_id = Column(String(12), ForeignKey("conversations.id"), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default=TaskStatus.PENDING.value)
    task_type = Column(String(20), default="immediate")
    schedule = Column(String(200), nullable=True)
    repeat = Column(String(20), default="none")
    priority = Column(String(10), default="normal")
    save_conversation = Column(Boolean, default=True)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    iterations = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)

    agent = relationship("Agent", back_populates="tasks")
    conversation = relationship("Conversation")
    messages = relationship("Message", back_populates="task", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(12), primary_key=True, default=gen_id)
    agent_id = Column(String(12), ForeignKey("agents.id"), nullable=False)
    title = Column(String(200), default="新对话")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(12), primary_key=True, default=gen_id)
    conversation_id = Column(String(12), ForeignKey("conversations.id"), nullable=False)
    task_id = Column(String(12), ForeignKey("tasks.id"), nullable=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, default="")
    tool_calls = Column(JSON, nullable=True)
    tool_call_id = Column(String(50), nullable=True)
    token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    task = relationship("Task", back_populates="messages")
