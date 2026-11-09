from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime

# ── Project Schemas ──────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str = Field(..., description="Project title")
    user_req: str = Field(..., description="User requirements / prompt")

class ProjectResponse(BaseModel):
    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    path: Optional[str] = None
    git_url: Optional[str] = None
    current_status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ── Task Schemas ─────────────────────────────────────────────
class TaskResponse(BaseModel):
    id: int
    workflow_id: Optional[int] = None
    requesting_agent_id: Optional[str] = None
    status: str
    request_details: Optional[str] = None
    payload: Optional[str] = None
    response: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ── Workflow Schemas ─────────────────────────────────────────
class WorkflowResponse(BaseModel):
    id: int
    project_id: Optional[int] = None
    current_state: str
    current_subgraph_node: Optional[str] = None
    completed_nodes: Optional[str] = "[]"  # JSON list of completed node names
    status: str
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    next_agent: Optional[str] = None
    summary: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ── Agent Log Schemas ────────────────────────────────────────
class AgentLogResponse(BaseModel):
    id: int
    workflow_id: Optional[int] = None
    requesting_agent_id: Optional[str] = None
    status: str
    request_details: Optional[str] = None
    payload: Optional[str] = None
    response: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ── Human Approval Schemas ───────────────────────────────────
class HumanApprovalResponse(BaseModel):
    id: int
    workflow_id: Optional[int] = None
    requesting_agent_id: Optional[str] = None
    status: str
    request_details: Optional[str] = None
    payload: Optional[str] = None
    feed_back: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class HumanApprovalSubmit(BaseModel):
    feedback: Optional[str] = ""

# ── Command Execution Schemas ────────────────────────────────
class CommandExecutionResponse(BaseModel):
    id: str
    project_id: int
    agent_role: str
    command: str
    cwd: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: int
    timestamp: datetime

    class Config:
        from_attributes = True

# ── File Record Schemas ──────────────────────────────────────
class FileRecordResponse(BaseModel):
    id: str
    project_id: int
    file_path: str
    action: str
    diff_snapshot: Optional[str] = None
    content_snapshot: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True
