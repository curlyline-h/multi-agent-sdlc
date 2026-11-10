"""
Backend Developer Agent — Subgraph Definition

Flow:
  START
    → pop_task
    → [router: if queue empty, END]
    → write_code
    → lint_code
    → [router: if lint fails, loop back to write_code]
    → run_tests
    → [router: if tests fail, loop back to write_code]
    → mark_task_complete
    → pop_task (Loop back to start)
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.src.agents.backend_dev.state import BackendDevState
from agents.src.agents.backend_dev.nodes import (
    pop_task_node,
    write_code_node,
    lint_code_node,
    run_tests_node,
    mark_task_complete_node,
    push_to_github_node
)

# ---------------------------------------------------------------------------
# Router: Is Queue Empty?
# ---------------------------------------------------------------------------
def _is_queue_empty(state: BackendDevState) -> str:
    """If there is no current task after popping, route to GitHub push."""
    return "push_to_github" if state.current_task is None else "write_code"

# ---------------------------------------------------------------------------
# Router: Did Linter Pass?
# ---------------------------------------------------------------------------
def _did_linter_pass(state: BackendDevState) -> str:
    """If there are linter errors, loop back to write_code."""
    max_iterations = 3
    if state.linter_errors and state.iteration_count < max_iterations:
        return "write_code"
    return "run_tests"

# ---------------------------------------------------------------------------
# Router: Did Tests Pass?
# ---------------------------------------------------------------------------
def _did_tests_pass(state: BackendDevState) -> str:
    """If there are test failures, loop back to write_code."""
    max_iterations = 3
    if state.test_failures and state.iteration_count < max_iterations:
        return "write_code"
    return "mark_task_complete"

# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
workflow = StateGraph(BackendDevState)

# Register all nodes
workflow.add_node("pop_task", pop_task_node)
workflow.add_node("write_code", write_code_node)
workflow.add_node("lint_code", lint_code_node)
workflow.add_node("run_tests", run_tests_node)
workflow.add_node("mark_task_complete", mark_task_complete_node)
workflow.add_node("push_to_github", push_to_github_node)

# Flow execution
workflow.add_edge(START, "pop_task")

# Routing based on queue state
workflow.add_conditional_edges(
    "pop_task",
    _is_queue_empty,
    {
        "END": END,
        "push_to_github": "push_to_github",
        "write_code": "write_code"
    }
)

workflow.add_edge("push_to_github", END)

workflow.add_edge("write_code", "lint_code")

# Routing based on linter results
workflow.add_conditional_edges(
    "lint_code",
    _did_linter_pass,
    {
        "write_code": "write_code",
        "run_tests": "run_tests"
    }
)

# Routing based on test results
workflow.add_conditional_edges(
    "run_tests",
    _did_tests_pass,
    {
        "write_code": "write_code",
        "mark_task_complete": "mark_task_complete"
    }
)
workflow.add_edge("mark_task_complete", "pop_task")

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

backend_dev_subgraph = workflow.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    from langchain_core.runnables import RunnableConfig
    from pathlib import Path
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Read the actual design doc for testing
    root_dir = Path(__file__).resolve().parents[4]
    design_path = root_dir / "final_design.md"
    try:
        design_content = design_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Could not find design doc at {design_path}")
        design_content = "No design found."
        
    initial_state = BackendDevState(
        final_design_doc=design_content,
        db_connection_string="mock_db_connection_string",
        workflow_tasks=[{"task_id": "backend_api_1", "description": "Create the POST /api/v1/contact endpoint for the contact form submissions, including Zod validation and Postgres insert. Ensure standard Next.js 14 API route structure."}],
    )
    
    config = RunnableConfig(recursion_limit=50, configurable={"thread_id": "test_thread"})
    print("Starting Backend Developer Agent...")
    
    for event in backend_dev_subgraph.stream(initial_state, config=config):
        for node_name, state_update in event.items():
            print(f"\n--- Node: {node_name} ---")
            if "current_code_draft" in state_update:
                print("Code drafted.")
            if "linter_errors" in state_update and state_update["linter_errors"]:
                print(f"Linter Errors: {state_update['linter_errors']}")
            if "test_failures" in state_update and state_update["test_failures"]:
                print(f"Test Failures: {state_update['test_failures']}")
                
    print("\nBackend Developer finished.")
