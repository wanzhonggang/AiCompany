import uuid
from typing import ClassVar
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Boolean, Integer, Enum as SAEnum, Index
from sqlalchemy.orm import relationship, validates
from .database import Base
from .time_utils import now_beijing
from .security import encrypt_data, decrypt_data
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
    
    # Encryption helpers - use ClassVar for non-database fields
    _api_key_plain: ClassVar[str | None] = None
    
    @validates("api_key")
    def _encrypt_api_key(self, key: str, value: str) -> str:
        if value and not value.startswith("gAAAAA"):  # Fernet tokens start with gAAAAA
            return encrypt_data(value)
        return value
    
    def get_api_key(self) -> str:
        # Create a per-instance cache instead of classvar
        if not hasattr(self, "_api_key_cache"):
            if self.api_key.startswith("gAAAAA"):
                self._api_key_cache = decrypt_data(self.api_key)
            else:
                self._api_key_cache = self.api_key
        return self._api_key_cache or ""
    
    def set_api_key(self, value: str):
        # Clear cache and set new value
        if hasattr(self, "_api_key_cache"):
            delattr(self, "_api_key_cache")
        self.api_key = encrypt_data(value)


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


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    
    id = Column(String(12), primary_key=True, default=gen_id)
    enterprise_id = Column(String(12), ForeignKey("enterprises.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)
    
    documents = relationship("KnowledgeDocument", back_populates="knowledge_base", cascade="all, delete-orphan")


class KnowledgeDocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    
    id = Column(String(12), primary_key=True, default=gen_id)
    knowledge_base_id = Column(String(12), ForeignKey("knowledge_bases.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer, default=0)
    status = Column(String(20), default=KnowledgeDocumentStatus.PENDING.value)
    content = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)
    
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(String(12), primary_key=True, default=gen_id)
    document_id = Column(String(12), ForeignKey("knowledge_documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    
    document = relationship("KnowledgeDocument", back_populates="chunks")


class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(String(12), primary_key=True, default=gen_id)
    enterprise_id = Column(String(12), ForeignKey("enterprises.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)
    
    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.order")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowStepType(str, enum.Enum):
    LLM = "llm"
    TOOL = "tool"
    CONDITION = "condition"
    WAIT = "wait"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    
    id = Column(String(12), primary_key=True, default=gen_id)
    workflow_id = Column(String(12), ForeignKey("workflows.id"), nullable=False)
    name = Column(String(200), nullable=False)
    step_type = Column(String(50), nullable=False)
    order = Column(Integer, nullable=False)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)
    
    workflow = relationship("Workflow", back_populates="steps")


class WorkflowExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"
    
    id = Column(String(12), primary_key=True, default=gen_id)
    workflow_id = Column(String(12), ForeignKey("workflows.id"), nullable=False)
    status = Column(String(20), default=WorkflowExecutionStatus.PENDING.value)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    
    workflow = relationship("Workflow", back_populates="executions")
    step_executions = relationship("WorkflowStepExecution", back_populates="execution", cascade="all, delete-orphan")


class WorkflowStepExecution(Base):
    __tablename__ = "workflow_step_executions"
    
    id = Column(String(12), primary_key=True, default=gen_id)
    execution_id = Column(String(12), ForeignKey("workflow_executions.id"), nullable=False)
    step_id = Column(String(12), ForeignKey("workflow_steps.id"), nullable=False)
    status = Column(String(20), default=WorkflowExecutionStatus.PENDING.value)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    
    execution = relationship("WorkflowExecution", back_populates="step_executions")
    step = relationship("WorkflowStep")


class QueuedTaskStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueuedTask(Base):
    __tablename__ = "queued_tasks"
    
    id = Column(String(12), primary_key=True, default=gen_id)
    enterprise_id = Column(String(12), ForeignKey("enterprises.id"), nullable=False)
    task_type = Column(String(100), nullable=False)
    payload = Column(JSON, default=dict)
    status = Column(String(20), default=QueuedTaskStatus.PENDING.value)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    priority = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing, onupdate=now_beijing)


# Indexes for better query performance
Index("idx_enterprise_llm_keys_enterprise_provider", EnterpriseLLMKey.enterprise_id, EnterpriseLLMKey.provider)
Index("idx_agents_enterprise", Agent.enterprise_id)
Index("idx_agents_department", Agent.department)
Index("idx_tasks_agent", Task.agent_id)
Index("idx_tasks_status", Task.status)
Index("idx_messages_conversation", Message.conversation_id)
Index("idx_conversations_agent", Conversation.agent_id)
Index("idx_operation_logs_enterprise", OperationLog.enterprise_id)
Index("idx_operation_logs_created", OperationLog.created_at)
Index("idx_departments_enterprise", Department.enterprise_id)
Index("idx_user_accounts_enterprise", UserAccount.enterprise_id)
Index("idx_knowledge_bases_enterprise", KnowledgeBase.enterprise_id)
Index("idx_knowledge_documents_base", KnowledgeDocument.knowledge_base_id)
Index("idx_document_chunks_document", DocumentChunk.document_id)
Index("idx_workflows_enterprise", Workflow.enterprise_id)
Index("idx_workflow_steps_workflow", WorkflowStep.workflow_id)
Index("idx_workflow_executions_workflow", WorkflowExecution.workflow_id)
Index("idx_workflow_step_executions_execution", WorkflowStepExecution.execution_id)
Index("idx_queued_tasks_enterprise", QueuedTask.enterprise_id)
Index("idx_queued_tasks_status", QueuedTask.status)
Index("idx_queued_tasks_scheduled", QueuedTask.scheduled_at)
