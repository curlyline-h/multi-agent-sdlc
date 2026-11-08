"""
Product Manager Agent — Subgraph Definition

SPLIT INTO TWO GRAPHS:

PHASE A: PRD Writing
  START → research → write_prd → user_approval → [revision loop] → finalize_prd → END

PHASE B: Jira + Slack
  START → create_slack_channel → create_jira_epic → create_jira_tickets → notify_slack → END
"""

from dotenv import load_dotenv
load_dotenv()
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents.src.agents.product_manager.state import ProductManagerState
from agents.src.agents.product_manager.nodes import (
    # Phase A
    research_node,
    write_prd_node,
    user_approval_node,
    finalize_prd_node,
    # Phase B
    create_slack_channel_node,
    create_jira_epic_node,
    create_jira_tickets_node,
    notify_slack_node,
)

# ===========================================================================
# PHASE A GRAPH (PRD Writing)
# ===========================================================================

def _should_revise_prd(state: ProductManagerState) -> str:
    """If user rejected the PRD draft, loop back to rewrite it."""
    return "finalize_prd" if state.is_approved else "write_prd"

phase_a = StateGraph(ProductManagerState)

phase_a.add_node("research", research_node)
phase_a.add_node("write_prd", write_prd_node)
phase_a.add_node("user_approval", user_approval_node)
phase_a.add_node("finalize_prd", finalize_prd_node)

phase_a.add_edge(START, "research")
phase_a.add_edge("research", "write_prd")
phase_a.add_edge("write_prd", "user_approval")

phase_a.add_conditional_edges(
    "user_approval",
    _should_revise_prd,
    {
        "write_prd": "write_prd",
        "finalize_prd": "finalize_prd",
    },
)

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

phase_a.add_edge("finalize_prd", END)
pm_phase_a_subgraph = phase_a.compile(checkpointer=checkpointer)

# ===========================================================================
# PHASE B GRAPH (Jira + Slack)
# ===========================================================================

phase_b = StateGraph(ProductManagerState)

phase_b.add_node("create_slack_channel", create_slack_channel_node)
phase_b.add_node("create_jira_epic", create_jira_epic_node)
phase_b.add_node("create_jira_tickets", create_jira_tickets_node)
phase_b.add_node("notify_slack", notify_slack_node)

phase_b.add_edge(START, "create_slack_channel")
phase_b.add_edge("create_slack_channel", "create_jira_epic")
phase_b.add_edge("create_jira_epic", "create_jira_tickets")
phase_b.add_edge("create_jira_tickets", "notify_slack")
phase_b.add_edge("notify_slack", END)

pm_phase_b_subgraph = phase_b.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    import os
    config = {"configurable": {"thread_id": "test-pm-001"}}

    print("Starting Product Manager Agent (Phase A)...")
    
    # Read the final_feasability_plan.md as the input for the Product Manager
    plan_path = os.path.join(os.path.dirname(__file__), "../../../../final_feasability_plan.md")
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            final_plan_content = f.read()
        print("Successfully loaded final_feasability_plan.md.")
    except FileNotFoundError:
        print(f"Warning: Could not find {plan_path}. Using a fallback plan.")
        final_plan_content = "This is a fallback final plan for an agentic SDLC system."
    
    print("Enter the raw user requirement to base the PRD on:")
    user_input = input("> ").strip()
    
    res = pm_phase_a_subgraph.invoke(
        {
            "user_req": user_input, 
            "final_plan": final_plan_content,
            "complexity_level": "medium",
            "project_type": "other"
        },
        config=config,
    )

    while True:
        state = pm_phase_a_subgraph.get_state(config)
        if not state.next:
            print("\nProduct Manager Workflow Finished!")
            print("Final Output:\n", state.values.get("prd", "No PRD generated."))
            break

        task = state.tasks[0]
        interrupt_val = task.interrupts[0]

        print(f"\n--- Paused at node: {state.next[0]} ---")
        
        payload = interrupt_val.value if hasattr(interrupt_val, "value") else interrupt_val
        
        if isinstance(payload, dict) and payload.get("type") == "prd_approval":
            print("\nDraft PRD created:")
            print("-" * 50)
            print(payload.get("draft"))
            print("-" * 50)
            print("Review the PRD draft. Type 'approve' or 'ok' to proceed, or write your feedback:")
        else:
            print(f"Interrupt payload: {interrupt_val}")

        print("\nEnter your response (or type 'exit' to quit):")
        user_reply = input("> ").strip()
        if user_reply.lower() == "exit":
            print("Exited.")
            break

        print("\nResuming Product Manager execution...")
        res = pm_phase_a_subgraph.invoke(
            Command(resume=user_reply),
            config=config
        )
