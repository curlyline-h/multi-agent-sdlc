"""
Planning Agent — Node Functions

Node execution order inside the subgraph:
  research → needs_clarification? → [interrupt for questions] →
  generate_draft → critique_draft → needs_revision? →
  [interrupt for user approval] → finalize

Each node returns a partial dict to update PlanningState.
"""
import json
import os
import re
from pathlib import Path
from typing import Any

from agents.src.shared.llm import get_llm, llm_invoke_with_retry, needs_external_research
from langchain_core.prompts import PromptTemplate
from langgraph.types import interrupt

from agents.src.agents.planning.state import PlanningState
from agents.src.agents.planning.tools import parse_structured_output
from agents.src.shared.tools import rag_search

# ---------------------------------------------------------------------------
# LLM setup  (swap model / provider to your preference)
# ---------------------------------------------------------------------------

_llm_draft = get_llm(temperature=0.7, max_tokens=4000, tier="heavy")

_llm_critique = get_llm(
    temperature=0.4,
    max_tokens=1500,
    tier="fast",
)

# ---------------------------------------------------------------------------
# Prompt loader helper
# ---------------------------------------------------------------------------
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Research Node
#    Runs web search (Tavily) + RAG search and stores results in state.
# ---------------------------------------------------------------------------

def research_node(state: PlanningState) -> dict:
    """
    Decides whether to perform RAG/web search based on the user request.
    If the request is a simple "create a new project from scratch", skips search to save time.
    """
    if not needs_external_research(state.user_req):
        return {
            "web_search_results": ["Skipped web search for new generic project."],
            "rag_results": ["Skipped internal RAG search for new generic project."],
        }

    # --- RAG search ---
    rag_result = rag_search.invoke({"query": state.user_req, "k": 5})
    rag_results = [rag_result] if rag_result else []

    # --- DuckDuckGo web search ---
    from agents.src.shared.llm import safe_web_search
    web_res = safe_web_search(state.user_req)
    web_results = [web_res] if isinstance(web_res, str) else list(web_res or [])

    return {
        "web_search_results": web_results,
        "rag_results": rag_results,
    }


# ---------------------------------------------------------------------------
# 2. Clarification Node
#    Decides if follow-up questions are needed and interrupts the graph
#    to wait for the user's answers if so.
# ---------------------------------------------------------------------------

def clarification_node(state: PlanningState) -> dict:
    """
    Uses the LLM to decide if the requirement is ambiguous. If yes, raises
    an interrupt so the UI can present questions to the user.
    """
    prompt_path = _PROMPTS_DIR / "planning_qa.txt"
    # Never loop endlessly once the user has already answered a round of questions
    if state.user_clarification_answers and "User answered:" in state.user_clarification_answers:
        return {"clarifying_questions": []}

    clarify_prompt = PromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    response = llm_invoke_with_retry(_llm_critique, clarify_prompt.format(
        user_req=state.user_req,
        qa_history=state.user_clarification_answers or "None"
    ), label="Planning-Clarify")
    from agents.src.shared.llm import extract_text_content
    content = extract_text_content(response).strip()

    # Strip out any <think>...</think> blocks from Qwen before checking for CLEAR
    clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    clear_token = re.sub(r'[^A-Z]', '', clean_content.upper())

    if clear_token == "CLEAR" or clean_content.upper().startswith("CLEAR"):
        return {"clarifying_questions": []}

    # Pass the entire conversational response back to the user
    questions = [clean_content]
    
    if questions:
        # Interrupt and wait for user input via the UI
        answers = interrupt({
            "type": "clarifying_questions",
            "questions": questions,
            "message": "The Planning Agent needs answers to these questions before proceeding.",
        })
        answers_str = answers if isinstance(answers, str) else str(answers)
        new_history = f"Questions asked:\n" + "\n".join(f"- {q}" for q in questions) + f"\nUser answered:\n{answers_str}\n\n"
        accumulated_history = (state.user_clarification_answers + "\n" + new_history).strip()
        
        return {
            "clarifying_questions": questions,
            "user_clarification_answers": accumulated_history,
        }

    return {"clarifying_questions": []}


# ---------------------------------------------------------------------------
# 3. Generate Draft Node
#    Produces the full feasibility brief + embedded JSON block.
# ---------------------------------------------------------------------------

def generate_draft_node(state: PlanningState) -> dict:
    """
    Generates the first (or revised) draft of the feasibility brief using
    the full planning prompt template.
    """
    template_str = _load_prompt("planning.txt")
    prompt = PromptTemplate.from_template(template_str)

    formatted = prompt.format(
        user_req=state.user_req,
        web_search_results=("\n\n".join(state.web_search_results) or "No web search results available.")[:1500],
        rag_results=("\n\n".join(state.rag_results) or "No internal knowledge base results found.")[:1500],
        user_clarification_answers=(state.user_clarification_answers or "No clarifications provided.")[:1500],
        critique_notes=(state.critique_notes or "No previous critique.")[:1500],
        previous_draft=(state.plan_draft or "No previous draft.")[:2500],
        user_feedback=(state.user_feedback or "No previous feedback.")[:1000],
    )

    response = llm_invoke_with_retry(_llm_draft, formatted, label="Planning-Draft")
    content = response.content
    clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    return {
        "plan_draft": clean_content,
        "iteration_count": state.iteration_count + 1,
    }


# ---------------------------------------------------------------------------
# 4. Critique Node
#    Self-evaluates the draft and produces notes for revision.
# ---------------------------------------------------------------------------

def critique_node(state: PlanningState) -> dict:
    """
    Runs the LLM against the critique prompt to identify weaknesses in the draft.
    """
    template_str = _load_prompt("planning_critique.txt")
    prompt = PromptTemplate.from_template(template_str)

    response = llm_invoke_with_retry(
        _llm_critique,
        prompt.format(user_req=state.user_req, plan_draft=state.plan_draft),
        label="Planning-Critique",
    )
    from agents.src.shared.llm import extract_text_content
    critique = extract_text_content(response).strip()
    return {"critique_notes": critique}


# ---------------------------------------------------------------------------
# 5. User Approval Node
#    Presents the refined draft to the user via LangGraph interrupt().
#    Waits for the user to approve or provide feedback.
# ---------------------------------------------------------------------------

def user_approval_node(state: PlanningState) -> dict:
    """
    Pauses the graph and presents the draft to the human user via the UI.
    The user can either approve (returns empty string) or provide feedback.
    """
    user_response = interrupt({
        "type": "plan_approval",
        "draft": state.plan_draft,
        "message": (
            "The Planning Agent has produced a feasibility brief. "
            "Please review it and either approve or provide feedback for revision."
        ),
    })

    # If the user approves (empty response or common approval phrases), mark as approved
    resp_norm = str(user_response or "").strip().lower()
    if not resp_norm or resp_norm in ("approve", "approved", "yes", "ok", "lgtm", "proceed", "looks good", "go ahead", "haan"):
        return {"user_feedback": "", "is_approved": True}

    # Otherwise capture the feedback for the next revision loop
    return {"user_feedback": str(user_response), "is_approved": False}


# ---------------------------------------------------------------------------
# 6. Finalize Node
#    Parses the structured JSON from the approved draft and writes final outputs.
# ---------------------------------------------------------------------------

def finalize_node(state: PlanningState) -> dict:
    """
    Extracts the structured JSON block from the approved plan_draft and
    writes all fields to the final output slots in the state.
    """
    structured = parse_structured_output.invoke({"raw_output": state.plan_draft})

    # Write the human-readable draft to a markdown file
    output_file = Path(__file__).resolve().parents[4] / "final_plan.md"
    output_file.write_text(state.plan_draft, encoding="utf-8")

    return {
        "final_plan": state.plan_draft,
        "complexity_level": structured.get("complexity_level", "medium"),
        "project_type": structured.get("project_type", "other"),

        "risks": structured.get("risks", []),
        "constraints": structured.get("constraints", []),
        "is_approved": True,
    }
