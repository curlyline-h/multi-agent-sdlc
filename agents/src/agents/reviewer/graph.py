"""
Reviewer Agent — Subgraph Definition

Flow:
  START → analyze_codebase → check_complexity → generate_review → submit_review → END
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.src.agents.reviewer.state import ReviewerState
from agents.src.agents.reviewer.nodes import (
    analyze_complexity_node,
    review_code_node,
    submit_review_node,
    pop_task_node,
    mark_task_complete_node
)

# ---------------------------------------------------------------------------
# Router: Is Queue Empty?
# ---------------------------------------------------------------------------
def _is_queue_empty(state: ReviewerState) -> str:
    return "END" if state.current_task is None else "analyze_complexity"

# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
workflow = StateGraph(ReviewerState)

# Register nodes
workflow.add_node("pop_task", pop_task_node)
workflow.add_node("analyze_complexity", analyze_complexity_node)
workflow.add_node("review_code", review_code_node)
workflow.add_node("submit_review", submit_review_node)
workflow.add_node("mark_task_complete", mark_task_complete_node)

# Flow execution
workflow.add_edge(START, "pop_task")
workflow.add_conditional_edges("pop_task", _is_queue_empty, {"END": END, "analyze_complexity": "analyze_complexity"})
workflow.add_edge("analyze_complexity", "review_code")
workflow.add_edge("review_code", "submit_review")
workflow.add_edge("submit_review", "mark_task_complete")
workflow.add_edge("mark_task_complete", "pop_task")

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

reviewer_subgraph = workflow.compile(checkpointer=checkpointer)
