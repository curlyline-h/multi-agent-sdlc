from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class PlanningState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    user_req: str = Field(description="Raw user requirement")

    # ── Research & iteration internals ────────────────────────────────────────
    web_search_results: List[str] = Field(
        default_factory=list,
        description="Accumulated web search results used for context"
    )
    rag_results: List[str] = Field(
        default_factory=list,
        description="Relevant chunks retrieved from the internal knowledge base"
    )
    clarifying_questions: List[str] = Field(
        default_factory=list,
        description="Questions the Planner wants to ask the user before drafting"
    )
    user_clarification_answers: str = Field(
        default="",
        description="Answers provided by the user to the clarifying questions"
    )
    plan_draft: str = Field(
        default="",
        description="Draft feasibility brief before critique and user approval"
    )
    critique_notes: str = Field(
        default="",
        description="Self-critique of the draft before presenting to the user"
    )
    user_feedback: str = Field(
        default="",
        description="User feedback after reviewing the draft (empty means approved)"
    )
    iteration_count: int = Field(
        default=0,
        description="Number of draft-critique-approval cycles completed"
    )

    # ── Structured analysis output ────────────────────────────────────────────
    complexity_level: str = Field(
        default="",
        description="Estimated project complexity: small | medium | large"
    )
    project_type: str = Field(
        default="",
        description="Project category: crud | data_pipeline | ai_integration | api_only | other"
    )

    risks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Identified risks: [{description, impact, mitigation}]"
    )
    constraints: List[str] = Field(
        default_factory=list,
        description="Hard constraints that must be respected by all downstream agents"
    )

    # ── Output ────────────────────────────────────────────────────────────────
    final_plan: str = Field(
        default="",
        description="Approved feasibility brief ready for the Product Manager"
    )
    is_approved: bool = Field(
        default=False,
        description="True once the user has approved the final plan"
    )
