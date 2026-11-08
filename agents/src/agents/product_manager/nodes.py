"""
Product Manager Agent — Node Functions

PHASE A: PRD Writing
  research → write_prd → user_approval → [revision loop] → finalize_prd

PHASE B: Jira + Slack (triggered separately after Task Breakdown)
  create_slack_channel_node → create_jira_epic_node → create_jira_tickets_node → notify_slack_node
"""
import re
from pathlib import Path
from typing import Any

from langchain_core.prompts import PromptTemplate
from agents.src.shared.llm import get_llm, llm_invoke_with_retry
from langgraph.types import interrupt

from agents.src.agents.product_manager.state import ProductManagerState
from agents.src.agents.product_manager.tools import (
    create_jira_epic,
    create_jira_tickets,
    create_slack_channel,
    post_slack_message,
)
from agents.src.shared.tools import rag_search

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
_llm = get_llm(
    temperature=0.4,
    max_tokens=4000 
)

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


# ============================================================================
# PHASE A — PRD WRITING
# ============================================================================

def research_node(state: ProductManagerState) -> dict:
    """
    Phase A — Step 1:
    Performs web search for competitor analysis and RAG search for past PRDs.
    Optionally skips this if the request is for a generic new project.
    """
    from langchain_core.prompts import PromptTemplate
    decision_prompt = PromptTemplate.from_template(
        "Does this user request require researching an existing internal codebase or finding external web documentation? "
        "Reply with ONLY 'YES' or 'NO'.\n\nRequest: {req}"
    )
    decision = llm_invoke_with_retry(_llm, decision_prompt.format(req=state.user_req)).content.strip().upper()
    
    import re
    decision = re.sub(r'<think>.*?</think>', '', decision, flags=re.DOTALL).strip()
    
    if "YES" not in decision:
        return {"web_search_results": ["Skipped web search for new generic project.", "Skipped internal RAG search for new generic project."]}

    # Web search (DuckDuckGo)
    from agents.src.shared.llm import safe_web_search
    web_results = safe_web_search(f"product requirements {state.user_req}")
    web_results = [web_results] if isinstance(web_results, str) else web_results

    # RAG search
    rag_raw = rag_search.invoke({"query": state.user_req, "k": 4})
    rag_results = [rag_raw] if rag_raw else []

    return {"web_search_results": web_results + rag_results}


def write_prd_node(state: ProductManagerState) -> dict:
    """
    Phase A — Step 2:
    Generates (or revises) the full PRD document from the planning brief.
    """
    template_str = _load_prompt("product_manager.txt")
    prompt = PromptTemplate.from_template(template_str)

    formatted = prompt.format(
        user_req=state.user_req,
        final_plan=state.final_plan or "No planning brief available.",
        web_search_results="\n\n".join(state.web_search_results) or "No research available.",
        constraints="\n".join(f"- {c}" for c in state.constraints) or "None specified.",
        risks="\n".join(
            f"- {r.get('description', '')} (Impact: {r.get('impact', 'Unknown')})"
            for r in state.risks
        ) or "None specified.",
        complexity_level=state.complexity_level or "medium",
        project_type=state.project_type or "other",
        previous_draft=(state.prd_draft or "No previous draft.")[:6000],
        user_feedback=state.user_feedback or "No previous feedback.",
    )

    llm_with_tools = _llm.bind_tools([rag_search, create_jira_epic, create_jira_tickets, create_slack_channel])
    response = llm_invoke_with_retry(llm_with_tools, formatted)
    content = response.content
    clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    return {
        "prd_draft": clean_content,
        "iteration_count": state.iteration_count + 1,
    }


def user_approval_node(state: ProductManagerState) -> dict:
    """
    Phase A — Step 3:
    Pauses the graph and presents the PRD draft to the user for review.
    The user can approve or provide targeted section-level feedback.
    """
    user_response = interrupt({
        "type": "prd_approval",
        "draft": state.prd_draft,
        "message": (
            "The Product Manager has completed the PRD. "
            "Please review and either approve, or provide specific feedback for revision."
        ),
    })

    if not user_response or str(user_response).strip().lower() in ("approve", "yes", "ok", ""):
        return {"user_feedback": "", "is_approved": True}

    return {"user_feedback": str(user_response), "is_approved": False}


def finalize_prd_node(state: ProductManagerState) -> dict:
    """
    Phase A — Step 4:
    Marks the approved PRD draft as the final PRD output.
    Also extracts a short project name for Slack channel naming.
    """
    # Derive a short slug for channel naming from the user requirement
    clean_req = re.sub(r"[^a-z0-9\s]", "", state.user_req.lower())
    words = [w for w in clean_req.split() if w not in ("i", "want", "you", "to", "a", "the", "create", "build", "make", "for", "me")]
    if not words:
        words = clean_req.split()[:3]
    slug = "-".join(words[:4]).strip("-")
    channel_name = f"proj-{slug}"[:80].strip("-")
    
    # Save the approved PRD to the workspace root
    workspace_root = Path(__file__).resolve().parents[4]
    prd_path = workspace_root / "final_prd.md"
    try:
        prd_path.write_text(state.prd_draft, encoding="utf-8")
    except Exception as e:
        print(f"Failed to write PRD to {prd_path}: {e}")

    return {
        "prd": state.prd_draft,
        "project_name": channel_name,
        "is_approved": True,
    }


# ============================================================================
# PHASE B — JIRA + SLACK INTEGRATION
# (Triggered after Task Breakdown Agent populates workflow_tasks)
# ============================================================================

def create_slack_channel_node(state: ProductManagerState) -> dict:
    """
    Phase B — Step 1:
    Creates a dedicated public channel for the project via Slack API.
    """
    try:
        result = create_slack_channel.invoke({"channel_name": state.project_name})
        return {
            "slack_channel_id": result.get("channel_id", "#general"),
            "slack_channel_name": result.get("channel_name", state.project_name),
        }
    except Exception as e:
        print(f"Failed to create Slack channel: {e}")
        # Fallback to general
        return {
            "slack_channel_id": "#general",
            "slack_channel_name": state.project_name,
        }


def create_jira_epic_node(state: ProductManagerState) -> dict:
    """
    Phase B — Step 2:
    Creates the parent Jira Epic for this project using the approved PRD as description.
    """
    import os
    jira_project_key = os.getenv("JIRA_PROJECT_KEY", "KAN")
    epic_name = state.project_name.replace("-", " ").title()

    try:
        result = create_jira_epic.invoke({
            "project_key": jira_project_key,
            "epic_name": epic_name,
            "description": state.prd[:5000],   # Jira description limit
            "priority": "High" if state.complexity_level == "large" else "Medium",
        })
        return {"jira_epic_key": result.get("epic_key", "")}
    except Exception as e:
        print(f"Failed to create Jira Epic: {e}")
        return {"jira_epic_key": "STUB-EPIC-1"}


def create_jira_tickets_node(state: ProductManagerState) -> dict:
    """
    Phase B — Step 3:
    Creates individual Jira tickets from each task in workflow_tasks,
    all linked under the parent Epic.
    """
    if not state.workflow_tasks:
        return {"jira_ticket_keys": []}

    import os
    jira_project_key = os.getenv("JIRA_PROJECT_KEY", "KAN")

    try:
        ticket_keys = create_jira_tickets.invoke({
            "project_key": jira_project_key,
            "epic_key": state.jira_epic_key,
            "tasks": state.workflow_tasks,
        })
        return {"jira_ticket_keys": ticket_keys}
    except Exception as e:
        print(f"Failed to create Jira tickets: {e}")
        stub_keys = [f"STUB-{i+2}" for i in range(len(state.workflow_tasks))]
        return {"jira_ticket_keys": stub_keys}


def notify_slack_node(state: ProductManagerState) -> dict:
    """
    Phase B — Step 4:
    Posts the project kickoff summary to the Slack channel via Official Slack SDK.
    """
    import os
    jira_base_url = f"{os.getenv('JIRA_URL', 'https://yourcompany.atlassian.net')}/browse"

    message_lines = [
        f"🚀 *Project Kickoff: {state.project_name.replace('-', ' ').title()}*",
        "",
        f"📋 *Jira Epic:* <{jira_base_url}/{state.jira_epic_key}|{state.jira_epic_key}>",
        "",
        f"🎫 *Tickets Created ({len(state.jira_ticket_keys)}):*",
    ]
    for key in state.jira_ticket_keys:
        message_lines.append(f"  • <{jira_base_url}/{key}|{key}>")

    message_lines += [
        "",
        "📐 *System Design:* Approved and available in the dashboard.",
        "📄 *PRD:* Approved and linked to the Epic.",
        "",
        "The AI build pipeline is now active. Updates will be posted here. 🤖",
    ]

    message = "\n".join(message_lines)

    try:
        post_slack_message.invoke({
            "channel_id": state.slack_channel_id,
            "message": message
        })
    except Exception as e:
        print("Failed to post to Slack via SDK:", str(e).encode('ascii', 'ignore').decode('ascii'))

    return {}
