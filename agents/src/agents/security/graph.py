"""
Security Agent — Subgraph Definition

Flow:
  START → run_sast → check_deps → analyze_vulnerabilities → enforce_security_gate → END
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.src.agents.security.state import SecurityState
from agents.src.agents.security.nodes import (
    run_sast_node,
    check_deps_node,
    analyze_vulnerabilities_node,
    enforce_security_gate_node,
    pop_task_node,
    mark_task_complete_node
)

# ---------------------------------------------------------------------------
# Router: Is Queue Empty?
# ---------------------------------------------------------------------------
def _is_queue_empty(state: SecurityState) -> str:
    return "END" if state.current_task is None else "run_sast"

# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
workflow = StateGraph(SecurityState)

# Register all nodes
workflow.add_node("pop_task", pop_task_node)
workflow.add_node("run_sast", run_sast_node)
workflow.add_node("check_deps", check_deps_node)
workflow.add_node("analyze_vulnerabilities", analyze_vulnerabilities_node)
workflow.add_node("enforce_security_gate", enforce_security_gate_node)
workflow.add_node("mark_task_complete", mark_task_complete_node)

# Flow execution
workflow.add_edge(START, "pop_task")
workflow.add_conditional_edges("pop_task", _is_queue_empty, {"END": END, "run_sast": "run_sast"})
workflow.add_edge("run_sast", "check_deps")
workflow.add_edge("check_deps", "analyze_vulnerabilities")
workflow.add_edge("analyze_vulnerabilities", "enforce_security_gate")
workflow.add_edge("enforce_security_gate", "mark_task_complete")
workflow.add_edge("mark_task_complete", "pop_task")

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

security_subgraph = workflow.compile(checkpointer=checkpointer)
