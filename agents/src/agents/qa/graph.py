"""
QA Agent — Subgraph Definition

Flow:
  START
    → generate_test_scripts
    → execute_tests
    → analyze_results
    → [router: if bugs found] → file_bug_reports → END
    → [router: if no bugs] → mark_qa_complete → END
    → pop_task
    → [router: if task] → generate_tests → execute_tests → analyze_failures → mark_task_complete → pop_task
    → [router: if empty] → END
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.src.agents.qa.state import QAState
from agents.src.agents.qa.nodes import (
    pop_task_node,
    generate_tests_node,
    execute_tests_node,
    analyze_failures_node,
    mark_task_complete_node
)

# ---------------------------------------------------------------------------
# Router: Is Queue Empty?
# ---------------------------------------------------------------------------
def _is_queue_empty(state: QAState) -> str:
    return "END" if state.current_task is None else "generate_tests"

# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
workflow = StateGraph(QAState)

# Register nodes
workflow.add_node("pop_task", pop_task_node)
workflow.add_node("generate_tests", generate_tests_node)
workflow.add_node("execute_tests", execute_tests_node)
workflow.add_node("analyze_failures", analyze_failures_node)
workflow.add_node("mark_task_complete", mark_task_complete_node)

# Flow execution
workflow.add_edge(START, "pop_task")

# Routing based on task availability
workflow.add_conditional_edges(
    "pop_task",
    _is_queue_empty,
    {
        "END": END,
        "generate_tests": "generate_tests"
    }
)

workflow.add_edge("generate_tests", "execute_tests")
workflow.add_edge("execute_tests", "analyze_failures")
workflow.add_edge("analyze_failures", "mark_task_complete")
workflow.add_edge("mark_task_complete", "pop_task")

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

qa_subgraph = workflow.compile(checkpointer=checkpointer)
