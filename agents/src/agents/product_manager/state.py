from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ProductManagerState(BaseModel):
    # ── Inputs from global state ──────────────────────────────────────────────
    user_req: str = Field(description="Raw user requirement")
    final_plan: str = Field(default="", description="Approved feasibility brief from Planning Agent")
    complexity_level: str = Field(default="medium", description="Project complexity from Planner")
    project_type: str = Field(default="other", description="Project type classification from Planner")
    constraints: List[str] = Field(default_factory=list, description="Hard constraints from Planner")
    risks: List[Dict[str, Any]] = Field(default_factory=list, description="Identified risks from Planner")

    # ── PRD writing internals ─────────────────────────────────────────────────
    web_search_results: List[str] = Field(
        default_factory=list,
        description="Competitor and domain research results"
    )
    prd_draft: str = Field(default="", description="Draft PRD before user approval")
    user_feedback: str = Field(
        default="",
        description="User feedback on the draft PRD (empty = approved)"
    )
    iteration_count: int = Field(default=0, description="Number of PRD revision cycles")
    is_approved: bool = Field(default=False, description="True once PRD is approved by user")

    # ── Phase B inputs (populated after Task Breakdown runs) ──────────────────
    workflow_tasks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Granular task list from Task Breakdown Agent"
    )
    final_design_doc: str = Field(
        default="",
        description="Approved System Design Document from the Architect"
    )
    project_name: str = Field(
        default="",
        description="Short project name used for Jira epic and Slack channel naming"
    )

    # ── Outputs ───────────────────────────────────────────────────────────────
    prd: str = Field(default="", description="Final approved PRD document")
    jira_epic_key: str = Field(default="", description="Jira Epic key created for this project")
    jira_ticket_keys: List[str] = Field(
        default_factory=list,
        description="List of individual Jira ticket keys created from tasks"
    )
    slack_channel_id: str = Field(
        default="",
        description="Slack channel ID created for this project"
    )
    slack_channel_name: str = Field(
        default="",
        description="Slack channel name (e.g. proj-uber-for-dogs)"
    )
