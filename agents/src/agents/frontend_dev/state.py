from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class FrontendDevState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    prd: str = Field(default="", description="Approved PRD (authoritative requirements)")
    final_design_doc: str = Field(description="Architecture design doc")
    github_repo_name: Optional[str] = Field(default=None, description="Name for the GitHub repo to push code to")
    
    # ── Task Queue ─────────────────────────────────────────────────────────────
    workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Uncompleted frontend tasks")
    completed_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Successfully implemented tasks")
    
    # ── Current Execution Context ──────────────────────────────────────────────
    current_task: Optional[Dict[str, Any]] = Field(default=None, description="The task currently being worked on")
    current_code_draft: str = Field(default="", description="Raw code generated for the current task")
    backend_api_schema: str = Field(default="", description="The fetched OpenAPI/Swagger JSON from the backend")
    linter_errors: str = Field(default="", description="Errors from the syntax checker")
    test_failures: str = Field(default="", description="Errors from running component tests")
    browser_console_errors: str = Field(default="", description="React/Vue runtime errors caught by headless browser")
    iteration_count: int = Field(default=0, description="Times the agent looped to fix the current task")
    
    # ── Output ─────────────────────────────────────────────────────────────────
    frontend_file_changes: List[Dict[str, Any]] = Field(default_factory=list, description="All frontend files modified")
    active_pr_number: int = Field(default=0, description="The PR number created by this agent")
    failed_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Tasks that still failed lint/tests after all retries")
