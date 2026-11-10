from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class QAState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    prd: str = Field(description="Product Requirements Document (for expected behavior)")
    final_design_doc: str = Field(description="Architecture doc")
    workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Assigned tasks from the Task Breakdown Agent")
    current_task: Optional[Dict[str, Any]] = Field(default=None, description="The task currently being executed")
    
    # ── Test Generation & Execution ────────────────────────────────────────────
    e2e_test_scripts: str = Field(default="", description="Generated automated test scripts")
    test_run_output: str = Field(default="", description="Logs from running Cypress/Playwright")
    
    # ── Bug Tracking ───────────────────────────────────────────────────────────
    discovered_bugs: List[Dict[str, str]] = Field(default_factory=list, description="Extracted bugs from test failures")
    jira_ticket_urls: List[str] = Field(default_factory=list, description="Links to the filed Jira bug reports")

    # ── Output ─────────────────────────────────────────────────────────────────
    all_tests_passed: bool = Field(default=False, description="True if the test suite is completely green")
    new_workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="New tasks generated if bugs are found")
    project_name: str = Field(default="", description="Project name slug")
    github_repo_name: str = Field(default="", description="GitHub repository name")
    active_pr_number: int = Field(default=0, description="Active PR number")
