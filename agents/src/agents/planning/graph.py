"""
Planning Agent — Subgraph Definition

Flow:
  START
    → research          (web search + RAG)
    → clarification     (interrupt if ambiguous questions exist)
    → generate_draft    (full feasibility brief + JSON block)
    → critique          (self-evaluation loop)
    → [revision check]  → generate_draft again if critique found issues
    → user_approval     (interrupt: user reviews and approves or gives feedback)
    → [approval check]  → generate_draft again if user rejected
    → finalize          (parse structured JSON, write final outputs)
  END
"""
from dotenv import load_dotenv
load_dotenv()  # Ensure .env is loaded before importing nodes which instantiate LLMs

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents.src.agents.planning.state import PlanningState
from agents.src.agents.planning.nodes import (
    research_node,
    clarification_node,
    generate_draft_node,
    critique_node,
    user_approval_node,
    finalize_node,
)

# ---------------------------------------------------------------------------
# Router: Should we generate the draft based on user clarification?
# ---------------------------------------------------------------------------


def _should_loop_clarification(state: PlanningState) -> str:
    """
    If the agent generated clarifying questions during this run, loop back to the node 
    to evaluate the new answers. If the agent said CLEAR (empty questions list), proceed to draft.
    """
    return "clarification" if state.clarifying_questions else "generate_draft"

# ---------------------------------------------------------------------------
# Router: Should we revise the draft based on critique?
# ---------------------------------------------------------------------------

def _should_revise_after_critique(state: PlanningState) -> str:
    """
    If the critique found issues and we haven't exceeded 1 iteration,
    loop back to generate another draft. Otherwise proceed to user approval.
    """
    max_iterations = 1
    has_issues = (
        state.critique_notes
        and "NO_ISSUES_FOUND" not in state.critique_notes.upper()
        and state.iteration_count < max_iterations
    )
    return "generate_draft" if has_issues else "user_approval"


# ---------------------------------------------------------------------------
# Router: Did the user approve the draft?
# ---------------------------------------------------------------------------

def _should_revise_after_feedback(state: PlanningState) -> str:
    """
    If the user provided feedback (rejected the draft), loop back to regenerate.
    If the user approved, proceed to finalize.
    """
    return "finalize" if state.is_approved else "generate_draft"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

workflow = StateGraph(PlanningState)

# Register nodes
workflow.add_node("research", research_node)
workflow.add_node("clarification", clarification_node)
workflow.add_node("generate_draft", generate_draft_node)
workflow.add_node("critique", critique_node)
workflow.add_node("user_approval", user_approval_node)
workflow.add_node("finalize", finalize_node)

# Edges: Linear flow up to the branching points
workflow.add_edge(START, "research")
workflow.add_edge("research", "clarification")
workflow.add_edge("generate_draft", "critique")

# Branch: Revision loop after critique
workflow.add_conditional_edges(
    "critique",
    _should_revise_after_critique,
    {
        "generate_draft": "generate_draft",
        "user_approval": "user_approval",
    },
)

# Branch: Revision loop after user feedback
workflow.add_conditional_edges(
    "user_approval",
    _should_revise_after_feedback,
    {
        "generate_draft": "generate_draft",
        "finalize": "finalize",
    },
)

workflow.add_conditional_edges(
    "clarification",
    _should_loop_clarification,
    {
        "generate_draft": "generate_draft",
        "clarification": "clarification",
    },
)

workflow.add_edge("finalize", END)

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

planning_subgraph = workflow.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "test-planning-001"}}

    print("Starting Planning Agent...")
    print("Hi there!")
    user_input=input()
    res = planning_subgraph.invoke(
        {"user_req": user_input},
        config=config,
    )

    while True:
        state = planning_subgraph.get_state(config)
        if not state.next:
            print("\nWorkflow Finished!")
            print(res)
            break

        task = state.tasks[0]
        interrupt_val = task.interrupts[0]

        print(f"\n--- Paused at node: {state.next[0]} ---")
        
        payload = interrupt_val.value if hasattr(interrupt_val, "value") else interrupt_val
        
        if isinstance(payload, dict) and payload.get("type") == "clarifying_questions":
            print("The Planning Agent says:")
            for q in payload.get("questions", []):
                print(f"{q}")
        elif isinstance(payload, dict) and payload.get("type") == "plan_approval":
            print("\nDraft feasibility brief created:")
            print("-" * 50)
            print(payload.get("draft"))
            print("-" * 50)
            print("Review the draft plan. Type 'approve' or 'ok' to proceed, or write your feedback:")
        else:
            print(f"Interrupt payload: {interrupt_val}")

        print("\nEnter your response (or type 'exit' to quit):")
        user_input = input("> ").strip()
        if user_input.lower() == "exit":
            print("Exited.")
            break

        print("\nResuming agent execution...")
        res = planning_subgraph.invoke(
            Command(resume=user_input),
            config=config
        )
