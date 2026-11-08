from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class DatabaseEngineerState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    project_name: str = Field(description="Name of the project to create an isolated DB for")
    final_design_doc: str = Field(description="Approved Architecture Design Document")
    workflow_tasks: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Assigned tasks from the Task Breakdown Agent"
    )
    current_task: Optional[Dict[str, Any]] = Field(
        default=None,
        description="The task currently being executed"
    )
    github_repo_name: Optional[str] = Field(
        default=None,
        description="Global GitHub repository name"
    )
    active_pr_number: Optional[int] = Field(
        default=None,
        description="Active Pull Request number"
    )

    # ── Execution internals ────────────────────────────────────────────────────
    db_connection_string: str = Field(
        default="", 
        description="Connection string for the newly created isolated database"
    )
    migration_logs: str = Field(
        default="", 
        description="stdout/stderr logs from the migration runner"
    )
    schema_diff_notes: str = Field(
        default="", 
        description="List of differences between the physical DB and the Design Doc"
    )
    iteration_count: int = Field(
        default=0, 
        description="Number of times the agent has tried to fix failing migrations"
    )

    # ── Outputs ────────────────────────────────────────────────────────────────
    db_schema_ready: bool = Field(
        default=False, 
        description="True when migrations succeed and schema validation passes"
    )
