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

_NON_REQUIREMENT_EXACT = {
    "hi", "hii", "hiii", "hiiii", "hiiiii", "hello", "helloo", "hellooo",
    "hey", "heyy", "heyyy", "hiya", "yo", "sup", "hola", "salam", "assalam",
    "assalamualaikum", "asalamualaikum", "aoa", "namaste", "greetings",
    "hi there", "hello there", "hey there", "good morning", "good afternoon",
    "good evening", "good night", "how are you", "how r u", "whats up",
    "what's up", "test", "testing", "ping", "ok", "okay", "k", "yes", "no",
    "thanks", "thank you", "thx", "who are you", "what can you do", "help",
    "approve", "approved", "proceed", "continue", "start",
}

_FILLER_WORDS = {
    "hi", "hii", "hiii", "hiiii", "hello", "helloo", "hey", "heyy", "hiya",
    "there", "bro", "dude", "friend", "sir", "madam", "bot", "ai", "assistant",
    "good", "morning", "afternoon", "evening", "night", "how", "are", "you",
    "doing", "whats", "what", "is", "up", "test", "testing", "ping", "ok",
    "okay", "yes", "yeah", "yep", "no", "nope", "please", "thanks", "thank",
    "can", "help", "me", "yo", "sup", "hola", "salam", "assalamualaikum",
    "aoa", "just", "saying", "checking", "in", "who", "do", "approve",
    "approved", "proceed", "continue", "start",
}


def _is_non_requirement_text(text: str) -> bool:
    """Returns True if text is empty, purely a greeting, small talk, or lacks any software requirement."""
    cleaned = re.sub(r"'", "", (text or "").lower())
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return True
    if cleaned in _NON_REQUIREMENT_EXACT:
        return True
    words = cleaned.split()
    if len(words) <= 6 and all(w in _FILLER_WORDS for w in words):
        return True
    return False


def _extract_user_answers(qa_history: str) -> list[str]:
    """Extracts each individual user answer from the accumulated Q&A history string."""
    if not qa_history:
        return []
    matches = re.findall(
        r"User answered:[ \t]*\r?\n?(.*?)(?=(?:\r?\n)*Questions asked:|\Z)",
        qa_history,
        flags=re.DOTALL,
    )
    return [m.strip() for m in matches]


def clarification_node(state: PlanningState) -> dict:
    """
    Uses the LLM to engage with the user and decide if a real software requirement
    has been provided and whether follow-up questions are needed.
    Never proceeds to drafting on greetings, small talk, or empty replies.
    """
    prompt_path = _PROMPTS_DIR / "planning_qa.txt"

    parsed_answers = _extract_user_answers(state.user_clarification_answers)
    orig_is_real = not _is_non_requirement_text(state.user_req)
    substantive_answers = [a for a in parsed_answers if not _is_non_requirement_text(a)]
    has_real_requirement = orig_is_real or len(substantive_answers) > 0

    # Count clarification rounds answered *after* a real project requirement was established.
    # If the original user_req was a greeting (e.g. "hi"), the first substantive answer
    # establishes the requirement itself and does NOT count as answering follow-up questions.
    post_req_answers = 0
    if has_real_requirement:
        if orig_is_real:
            post_req_answers = len([a for a in parsed_answers if a])
        else:
            # Find index of first substantive answer; count non-empty answers after it
            first_real_idx = next(
                (i for i, a in enumerate(parsed_answers) if not _is_non_requirement_text(a)),
                len(parsed_answers),
            )
            post_req_answers = len([a for a in parsed_answers[first_real_idx + 1:] if a])

    # Cap endless loops ONLY once a real requirement exists AND the user has answered
    # at least 2 follow-up clarification rounds.
    if has_real_requirement and post_req_answers >= 2:
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

    is_clear = clear_token == "CLEAR" or clean_content.upper().startswith("CLEAR")

    # HARD GUARD: Never allow CLEAR (or drafting) if no real software requirement exists yet
    if is_clear and has_real_requirement:
        return {"clarifying_questions": []}

    if is_clear or not clean_content:
        clean_content = (
            "Hello! I'm the Planning Agent. Whenever you're ready, tell me about the "
            "software project, app, or feature you'd like to build, and I'll help you plan it out!"
        )

    # Pass the entire conversational response back to the user via ask_clarification_node
    # (kept in a separate node so LangGraph interrupt replay never re-invokes the LLM).
    return {"clarifying_questions": [clean_content]}


def ask_clarification_node(state: PlanningState) -> dict:
    """
    Pure interrupt node (no LLM calls) that pauses to collect the user's reply
    to the planner's greeting or clarifying questions.
    """
    questions = state.clarifying_questions or [
        "Hello! I'm the Planning Agent. What software project, app, or feature would you like to build today?"
    ]
    answers = interrupt({
        "type": "clarifying_questions",
        "questions": questions,
        "message": "The Planning Agent needs answers to these questions before proceeding.",
    })
    answers_str = (answers if isinstance(answers, str) else str(answers or "")).strip()
    new_history = (
        f"Questions asked:\n"
        + "\n".join(f"- {q}" for q in questions)
        + f"\nUser answered:\n{answers_str}\n\n"
    )
    accumulated_history = (state.user_clarification_answers + "\n" + new_history).strip()

    update: dict[str, Any] = {
        "clarifying_questions": [],
        "user_clarification_answers": accumulated_history,
    }

    # If the initial user_req was just a greeting/non-requirement and the user has now
    # provided an actual software requirement, promote it to user_req so downstream
    # research, planning draft, and PRD use the real requirement instead of "hi".
    if _is_non_requirement_text(state.user_req) and not _is_non_requirement_text(answers_str):
        update["user_req"] = answers_str

    return update


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
