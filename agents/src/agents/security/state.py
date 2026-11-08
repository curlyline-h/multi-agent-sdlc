from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class SecurityState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    backend_file_changes: List[Dict[str, Any]] = Field(default_factory=list, description="Backend code written")
    frontend_file_changes: List[Dict[str, Any]] = Field(default_factory=list, description="Frontend code written")
    workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Assigned tasks from the Task Breakdown Agent")
    current_task: Optional[Dict[str, Any]] = Field(default=None, description="The task currently being executed")
    
    # ── Internal State ─────────────────────────────────────────────────────────
    sast_scan_results: str = Field(default="", description="Output from Bandit/Semgrep static analysis")
    dependency_vulnerabilities: str = Field(default="", description="Output from Snyk/npm audit")
    security_report: str = Field(default="", description="Generated summary of found vulnerabilities")
    
    # ── Outputs ─────────────────────────────────────────────────────────────────
    security_approved: bool = Field(default=False, description="True if no blockers found")
    new_workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="New tasks to fix vulnerabilities")
    internal_vulnerabilities: List[Dict[str, Any]] = Field(default_factory=list, description="Internal parsed vulns")
