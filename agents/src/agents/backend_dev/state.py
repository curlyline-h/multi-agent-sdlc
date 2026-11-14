from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class BackendDevState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    final_design_doc: str = Field(description="Architecture design doc")
    db_connection_string: str = Field(default="", description="Connection string to the physical DB")
    github_repo_name: Optional[str] = Field(default=None, description="Name for the GitHub repo to push code to")
    
    # ── Task Queue ─────────────────────────────────────────────────────────────
    workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Uncompleted backend tasks")
    completed_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Successfully implemented tasks")
    
    # ── Current Execution Context ──────────────────────────────────────────────
    current_task: Optional[Dict[str, Any]] = Field(default=None, description="The task currently being worked on")
    current_code_draft: str = Field(default="", description="Raw code generated for the current task")
    linter_errors: str = Field(default="", description="Errors from the syntax checker")
    test_failures: str = Field(default="", description="Errors from running unit tests")
    iteration_count: int = Field(default=0, description="Times the agent looped to fix the current task")
    
    # ── Output ─────────────────────────────────────────────────────────────────
    backend_file_changes: List[Dict[str, Any]] = Field(default_factory=list, description="All backend files modified")
    active_pr_number: int = Field(default=0, description="The PR number created by this agent")
