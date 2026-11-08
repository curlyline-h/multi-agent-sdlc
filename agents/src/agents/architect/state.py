from pydantic import BaseModel, Field
from typing import List, Dict, Any
class ArchitectState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    user_req: str = Field(description="Raw user requirement")
    prd: str = Field(default="", description="Approved PRD from the Product Manager Agent")
    complexity_level: str = Field(default="medium", description="Project complexity from Planner")
    project_type: str = Field(default="other", description="Project type from Planner")
    constraints: List[str] = Field(default_factory=list, description="Hard constraints from Planner")

    # ── Research internals ────────────────────────────────────────────────────
    web_search_results: List[str] = Field(
        default_factory=list,
        description="Technical reference search results"
    )
    rag_results: List[str] = Field(
        default_factory=list,
        description="Past design docs retrieved from internal knowledge base"
    )
    # ── Design drafting internals ─────────────────────────────────────────────
    system_design_draft: str = Field(
        default="",
        description="Full draft of the system design document"
    )
    schema_validation_notes: str = Field(
        default="",
        description="Notes from the schema validator tool"
    )
    api_validation_notes: str = Field(
        default="",
        description="Notes from the API spec linter tool"
    )
    self_critique_notes: str = Field(
        default="",
        description="Architect's self-critique of the design draft"
    )
    iteration_count: int = Field(default=0, description="Number of design revision cycles")
    # ── Section-level user approval tracking ─────────────────────────────────
    schema_approved: bool = Field(default=False, description="Database schema section approved by user")
    api_approved: bool = Field(default=False, description="API endpoints section approved by user")
    structure_approved: bool = Field(default=False, description="Directory structure section approved by user")
    schema_feedback: str = Field(default="", description="User feedback on database schema section")
    api_feedback: str = Field(default="", description="User feedback on API endpoints section")
    structure_feedback: str = Field(default="", description="User feedback on directory structure section")
    # ── Output ────────────────────────────────────────────────────────────────
    final_design_doc: str = Field(
        default="",
        description="Final, fully approved System Design Document"
    )