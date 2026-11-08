from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ReviewerState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    backend_file_changes: List[Dict[str, Any]] = Field(default_factory=list, description="Backend code written")
    frontend_file_changes: List[Dict[str, Any]] = Field(default_factory=list, description="Frontend code written")
    workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Assigned tasks from the Task Breakdown Agent")
    current_task: Optional[Dict[str, Any]] = Field(default=None, description="The task currently being executed")
    active_pr_number: int = Field(default=0, description="The GitHub PR number to review")
    github_repo_name: str = Field(default="", description="The repository name for GitHub API calls")
    
    # ── Internal State ─────────────────────────────────────────────────────────
    complexity_report: str = Field(default="", description="Output of static analysis tools")
    code_review_comments: str = Field(default="", description="Generated PR comments based on best practices")

    # ── Outputs ─────────────────────────────────────────────────────────────────
    code_review_approved: bool = Field(default=False, description="True if the code passes all standards")
    new_workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="New tasks generated if review fails")
