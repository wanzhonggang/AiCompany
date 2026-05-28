import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Boolean, Integer, Enum as SAEnum
from sqlalchemy.orm import relationship
from .database import Base
from .time_utils import now_beijing
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


class Enterprise(Base):
    __tablename__ = "enterprises"

    id = Column(String(12), primary_key=True, default=gen_id)
    name = Column(String(120), nullable=False)
    plan = Column(String(20), default="trial")
    billing_period = Column(String(20), default="monthly")
    payment_status = Column(String(20), default="trial")
    default_provider = Column(String(50), default="")
    default_model = Column(String(150), default="")
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)

    users = relationship("UserAccount", back_populates="enterprise", cascade="all, delete-orphan")


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id = Column(String(12), primary_key=True, default=gen_id)
    enterprise_id = Column(String(12), ForeignKey("enterprises.id"), nullable=False)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(300), nullable=False)
    role = Column(String(20), default="admin")
    agent_id = Column(String(12), ForeignKey("agents.id"), nullable=True)
    display_name = Column(String(100), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)

    enterprise = relationship("Enterprise", back_populates="users")
    agent = relationship("Agent")


class EnterpriseLLMKey(Base):
    __tablename__ = "enterprise_llm_keys"

    id = Column(String(12), primary_key=True, default=gen_id)
    enterprise_id = Column(String(12), ForeignKey("enterprises.id"), nullable=False)
    provider = Column(String(50), nullable=False)
    api_key = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(String(12), primary_key=True, default=gen_id)
    enterprise_id = Column(String(12), ForeignKey("enterprises.id"), nullable=False)
    actor_user_id = Column(String(12), ForeignKey("user_accounts.id"), nullable=True)
    actor_username = Column(String(80), default="")
    actor_role = Column(String(20), default="")
    actor_agent_id = Column(String(12), nullable=True)
    actor_agent_name = Column(String(100), default="")
    action = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(String(12), nullable=True)
    target_name = Column(String(200), default="")
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=now_beijing)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(12), primary_key=True, default=gen_id)
    enterprise_id = Column(String(12), ForeignKey("enterprises.id"), nullable=True)
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
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)

    tasks = relationship("Task", back_populates="agent", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="agent", cascade="all, delete-orphan")
    tool_bindings = relationship("AgentToolBinding", back_populates="agent", cascade="all, delete-orphan")
    profile = relationship("AgentProfile", back_populates="agent", cascade="all, delete-orphan", uselist=False)
    routines = relationship("AgentRoutine", back_populates="agent", cascade="all, delete-orphan")
    integrations = relationship("AgentIntegration", back_populates="agent", cascade="all, delete-orphan")


class Department(Base):
    __tablename__ = "departments"

    id = Column(String(12), primary_key=True, default=gen_id)
    enterprise_id = Column(String(12), ForeignKey("enterprises.id"), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    color = Column(String(7), default="#06b6d4")
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)


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


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    agent_id = Column(String(12), ForeignKey("agents.id"), primary_key=True)
    mission = Column(Text, default="")
    responsibilities = Column(Text, default="")
    daily_tasks = Column(Text, default="")
    sop = Column(Text, default="")
    account_notes = Column(Text, default="")
    communication_rules = Column(Text, default="")
    approval_rules = Column(Text, default="")
    work_style = Column(Text, default="")
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)

    agent = relationship("Agent", back_populates="profile")


class AgentRoutine(Base):
    __tablename__ = "agent_routines"

    id = Column(String(12), primary_key=True, default=gen_id)
    agent_id = Column(String(12), ForeignKey("agents.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    schedule_type = Column(String(20), default="daily")
    schedule_time = Column(String(5), default="09:00")
    cron_expression = Column(String(100), nullable=True)
    enabled = Column(Boolean, default=True)
    save_conversation = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)

    agent = relationship("Agent", back_populates="routines")


class AgentIntegration(Base):
    __tablename__ = "agent_integrations"

    id = Column(String(12), primary_key=True, default=gen_id)
    agent_id = Column(String(12), ForeignKey("agents.id"), nullable=False)
    provider = Column(String(30), nullable=False)
    name = Column(String(100), nullable=False)
    account_label = Column(String(200), default="")
    config = Column(JSON, default=dict)
    enabled = Column(Boolean, default=True)
    last_test_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)

    agent = relationship("Agent", back_populates="integrations")


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
    created_at = Column(DateTime, default=now_beijing)
    assigned_at = Column(DateTime, default=now_beijing)
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
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)

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
    created_at = Column(DateTime, default=now_beijing)

    conversation = relationship("Conversation", back_populates="messages")
    task = relationship("Task", back_populates="messages")
