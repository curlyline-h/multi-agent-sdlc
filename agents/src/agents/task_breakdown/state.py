from pydantic import BaseModel, Field
from typing import List, Dict, Any

class TaskBreakdownState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    prd: str = Field(description="Product Requirements Document")
    final_design_doc: str = Field(description="System design plan")

    # ── Outputs ─────────────────────────────────────────────────────────────────
    workflow_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="List of granular JSON tasks for developers")
