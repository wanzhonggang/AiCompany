from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ---- Auth / SaaS ----
class EnterpriseRegisterRequest(BaseModel):
    enterprise_name: str = Field(..., min_length=1, max_length=120)
    admin_username: str = Field(..., min_length=3, max_length=80)
    admin_password: str = Field(..., min_length=6, max_length=100)
    plan: str = Field(default="formal", pattern="^(trial|formal)$")
    billing_period: str = Field(default="monthly", pattern="^(monthly|yearly)$")
    payment_method: str = Field(default="wechat", pattern="^(wechat|alipay)$")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=100)


class PasswordChangeRequest(BaseModel):
    old_password: Optional[str] = Field(default=None, max_length=100)
    new_password: str = Field(..., min_length=6, max_length=100)


class PasswordUpdateResponse(BaseModel):
    ok: bool = True
    username: Optional[str] = None


class AdminCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=6, max_length=100)
    display_name: str = Field(default="企业管理员", max_length=100)


class AdminResponse(BaseModel):
    id: str
    username: str
    display_name: str
    enabled: bool
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class OperationLogResponse(BaseModel):
    id: str
    actor_username: str
    actor_role: str
    actor_agent_id: Optional[str] = None
    actor_agent_name: str = ""
    action: str
    target_type: str
    target_id: Optional[str]
    target_name: str
    detail: str
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AuthUserResponse(BaseModel):
    id: str
    username: str
    role: str
    enterprise_id: str
    enterprise_name: str
    agent_id: Optional[str] = None
    display_name: str = ""


class AuthResponse(BaseModel):
    token: str
    user: AuthUserResponse
    payment_required: bool = False
    payment: Optional[dict] = None


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
    runtime_mode: str = Field(default="local_client", pattern="^(local_client|cloud_pool)$")
    workstation_id: Optional[str] = Field(default=None, max_length=12)


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
    runtime_mode: Optional[str] = Field(default=None, pattern="^(local_client|cloud_pool)$")
    workstation_id: Optional[str] = Field(default=None, max_length=12)


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
    employee_username: Optional[str] = None
    employee_init_password: Optional[str] = None
    runtime_mode: str = "local_client"
    workstation_id: Optional[str] = None
    workstation_name: Optional[str] = None
    workstation_kind: Optional[str] = None
    workstation_status: Optional[str] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---- Workstation ----
class WorkstationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(default="local", pattern="^(local|cloud)$")
    status: str = Field(default="offline", pattern="^(offline|online|available|busy|maintenance)$")
    host: str = Field(default="", max_length=200)
    ip_address: str = Field(default="", max_length=80)
    login_username: str = Field(default="", max_length=120)
    login_password: Optional[str] = Field(default=None, max_length=400)
    client_version: str = Field(default="", max_length=50)
    notes: str = Field(default="", max_length=2000)


class WorkstationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    kind: Optional[str] = Field(default=None, pattern="^(local|cloud)$")
    status: Optional[str] = Field(default=None, pattern="^(offline|online|available|busy|maintenance)$")
    host: Optional[str] = Field(default=None, max_length=200)
    ip_address: Optional[str] = Field(default=None, max_length=80)
    login_username: Optional[str] = Field(default=None, max_length=120)
    login_password: Optional[str] = Field(default=None, max_length=400)
    client_version: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=2000)


class WorkstationConnectivityRequest(BaseModel):
    host: str = Field(default="", max_length=200)


class WorkstationConnectivityResponse(BaseModel):
    ok: bool
    host: str
    port: int
    message: str


class WorkstationResponse(BaseModel):
    id: str
    name: str
    kind: str
    status: str
    host: str
    ip_address: str
    login_username: str
    password_set: bool = False
    client_version: str
    bind_code: str
    notes: str
    assigned_agent_count: int = 0
    last_seen_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class WorkstationClientBindRequest(BaseModel):
    bind_code: str = Field(..., min_length=4, max_length=32)
    machine_name: str = Field(default="", max_length=120)
    ip_address: str = Field(default="", max_length=80)
    client_version: str = Field(default="", max_length=50)
    system_info: str = Field(default="", max_length=1000)


class WorkstationClientBindResponse(BaseModel):
    ok: bool = True
    workstation_id: str
    name: str
    enterprise_id: str


# ---- Department ----
class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    color: str = Field(default="#06b6d4", max_length=7)


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    color: Optional[str] = Field(default=None, max_length=7)


class DepartmentResponse(BaseModel):
    id: str
    name: str
    description: str
    color: str
    member_count: int = 0
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


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    task_type: Optional[str] = Field(default=None, pattern="^(immediate|scheduled)$")
    schedule: Optional[str] = Field(default=None, max_length=200)
    repeat: Optional[str] = Field(default=None, pattern="^(none|daily|weekly)$")
    priority: Optional[str] = Field(default=None, max_length=10)
    save_conversation: Optional[bool] = None
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


class SmartTaskRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=20000)
    save_conversation: bool = True


class SmartTaskItem(BaseModel):
    title: str
    description: str = ""
    task_type: str = "immediate"
    schedule: Optional[str] = None
    repeat: str = "none"
    priority: str = "normal"
    next_run_at: Optional[str] = None


class IntegrationFieldRequirement(BaseModel):
    key: str
    label: str
    placeholder: str = ""
    required: bool = False


class IntegrationRequirement(BaseModel):
    provider: str
    name: str
    account_label: str = ""
    reason: str = ""
    access_method: str = "web"
    fields: list[IntegrationFieldRequirement] = Field(default_factory=list)


class SmartTaskPlanResponse(BaseModel):
    action: str = "task"
    tasks: list[SmartTaskItem]
    requirements: list[IntegrationRequirement] = Field(default_factory=list)
    source: str = "fallback"


# ---- Agent memory / profile ----
class AgentProfileUpdate(BaseModel):
    mission: str = Field(default="", max_length=8000)
    responsibilities: str = Field(default="", max_length=12000)
    daily_tasks: str = Field(default="", max_length=12000)
    sop: str = Field(default="", max_length=20000)
    account_notes: str = Field(default="", max_length=12000)
    communication_rules: str = Field(default="", max_length=8000)
    approval_rules: str = Field(default="", max_length=8000)
    work_style: str = Field(default="", max_length=8000)


class AgentProfileResponse(AgentProfileUpdate):
    agent_id: str
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AgentRoutineCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    schedule_type: str = Field(default="daily", pattern="^(daily|weekly|monthly|cron)$")
    schedule_time: str = Field(default="09:00", max_length=5)
    cron_expression: Optional[str] = Field(default=None, max_length=100)
    enabled: bool = True
    save_conversation: bool = True
    next_run_at: Optional[datetime] = None


class AgentRoutineUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    schedule_type: Optional[str] = Field(default=None, pattern="^(daily|weekly|monthly|cron)$")
    schedule_time: Optional[str] = Field(default=None, max_length=5)
    cron_expression: Optional[str] = Field(default=None, max_length=100)
    enabled: Optional[bool] = None
    save_conversation: Optional[bool] = None
    next_run_at: Optional[datetime] = None


class AgentRoutineResponse(BaseModel):
    id: str
    agent_id: str
    title: str
    description: str
    schedule_type: str
    schedule_time: str
    cron_expression: Optional[str]
    enabled: bool
    save_conversation: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AgentIntegrationCreate(BaseModel):
    provider: str = Field(..., pattern="^(feishu|wecom|qq|wechat|browser|other)$")
    name: str = Field(..., min_length=1, max_length=100)
    account_label: str = Field(default="", max_length=200)
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class AgentIntegrationUpdate(BaseModel):
    provider: Optional[str] = Field(default=None, pattern="^(feishu|wecom|qq|wechat|browser|other)$")
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    account_label: Optional[str] = Field(default=None, max_length=200)
    config: Optional[dict] = None
    enabled: Optional[bool] = None


class AgentIntegrationResponse(BaseModel):
    id: str
    agent_id: str
    provider: str
    name: str
    account_label: str
    config: dict
    enabled: bool
    last_test_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---- Stats ----
class StatsResponse(BaseModel):
    total: int
    working: int
    idle: int
    blocked: int
    completed: int


# ---- Knowledge Base ----
class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    is_public: bool = False


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    is_public: Optional[bool] = None


class KnowledgeBaseResponse(BaseModel):
    id: str
    enterprise_id: str
    name: str
    description: str
    is_public: bool
    document_count: int = 0
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class KnowledgeDocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    error_message: Optional[str] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DocumentChunkResponse(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    content: str
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class KnowledgeRetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    knowledge_base_ids: Optional[List[str]] = None
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeRetrievalResult(BaseModel):
    chunk: DocumentChunkResponse
    document: KnowledgeDocumentResponse
    score: float


class KnowledgeRetrievalResponse(BaseModel):
    query: str
    results: List[KnowledgeRetrievalResult]


# ---- Workflow ----
class WorkflowStepCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    step_type: str = Field(..., min_length=1, max_length=50)
    order: int = Field(..., ge=0)
    config: dict = Field(default_factory=dict)


class WorkflowStepUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    step_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    order: Optional[int] = Field(default=None, ge=0)
    config: Optional[dict] = None


class WorkflowStepResponse(BaseModel):
    id: str
    workflow_id: str
    name: str
    step_type: str
    order: int
    config: dict
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    enabled: bool = True
    steps: List[WorkflowStepCreate] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    enabled: Optional[bool] = None


class WorkflowResponse(BaseModel):
    id: str
    enterprise_id: str
    name: str
    description: str
    enabled: bool
    steps: List[WorkflowStepResponse] = Field(default_factory=list)
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class WorkflowExecutionCreate(BaseModel):
    workflow_id: Optional[str] = Field(default=None, min_length=1, max_length=12)
    input_data: dict = Field(default_factory=dict)


class WorkflowExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    input_data: dict
    output_data: Optional[dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class WorkflowStepExecutionResponse(BaseModel):
    id: str
    execution_id: str
    step_id: str
    status: str
    input_data: dict
    output_data: Optional[dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---- Queued Task ----
class QueuedTaskCreate(BaseModel):
    task_type: str = Field(..., min_length=1, max_length=100)
    payload: dict = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0)
    scheduled_at: Optional[datetime] = None


class QueuedTaskResponse(BaseModel):
    id: str
    enterprise_id: str
    task_type: str
    payload: dict
    status: str
    result: Optional[dict] = None
    error_message: Optional[str] = None
    priority: int
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
