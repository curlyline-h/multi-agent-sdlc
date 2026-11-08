from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class DevOpsState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    final_design_doc: str = Field(description="Architecture doc detailing infrastructure requirements")
    source_code_paths: List[str] = Field(default_factory=list, description="Paths to the built backend/frontend code")
    workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Assigned tasks from the Task Breakdown Agent")
    current_task: Optional[Dict[str, Any]] = Field(default=None, description="The task currently being executed")
    github_repo_name: Optional[str] = Field(default=None, description="Name for the GitHub repo to create and push to")
    
    # ── Planning & Validation ──────────────────────────────────────────────────
    deployment_plan: str = Field(default="", description="Generated IaC, Dockerfiles, and CI scripts")
    deployment_commands: List[str] = Field(default_factory=list, description="Shell commands needed to deploy the app")
    iac_validation_notes: str = Field(default="", description="Linter output from validate_iac_config tool")
    iteration_count: int = Field(default=0, description="Number of times the agent tried to fix IaC bugs")
    active_pr_number: int = Field(default=0, description="The PR number created by this agent")
    
    # ── Human Approval ─────────────────────────────────────────────────────────
    deployment_approved: bool = Field(default=False, description="Whether the user approved the physical deployment")
    deployment_feedback: str = Field(default="", description="User feedback if the deployment plan was rejected")

    # ── Execution Outputs ──────────────────────────────────────────────────────
    deployment_logs: str = Field(default="", description="Logs from running docker/terraform/kubectl")
    health_check_status: str = Field(default="", description="Output of the live ping to the deployed service")
