"""
Frontend Developer Agent — Subgraph Definition

Flow:
  START
    → pop_task
    → [router: if empty, END]
    → write_ui_code
    → lint_code
    → [router: loop if lint fails]
    → run_tests
    → [router: loop if tests fail]
    → browser_check
    → [router: loop if console errors]
    → mark_task_complete
    → pop_task (Loop back)
"""
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.src.agents.frontend_dev.state import FrontendDevState
from agents.src.agents.frontend_dev.nodes import (
    pop_task_node,
    write_ui_code_node,
    lint_code_node,
    run_tests_node,
    browser_check_node,
    mark_task_complete_node,
    push_to_github_node
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
def _is_queue_empty(state: FrontendDevState) -> str:
    return "push_to_github" if state.current_task is None else "write_ui_code"

def _did_linter_pass(state: FrontendDevState) -> str:
    max_iterations = 3
    if state.linter_errors and state.iteration_count < max_iterations:
        return "write_ui_code"
    return "run_tests"

def _did_tests_pass(state: FrontendDevState) -> str:
    max_iterations = 3
    if state.test_failures and state.iteration_count < max_iterations:
        return "write_ui_code"
    return "browser_check"

def _is_console_clean(state: FrontendDevState) -> str:
    max_iterations = 3
    if state.browser_console_errors and state.iteration_count < max_iterations:
        return "write_ui_code"
    return "mark_task_complete"

# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
workflow = StateGraph(FrontendDevState)

# Register nodes
workflow.add_node("pop_task", pop_task_node)
workflow.add_node("write_ui_code", write_ui_code_node)
workflow.add_node("lint_code", lint_code_node)
workflow.add_node("run_tests", run_tests_node)
workflow.add_node("browser_check", browser_check_node)
workflow.add_node("mark_task_complete", mark_task_complete_node)
workflow.add_node("push_to_github", push_to_github_node)

# Flow execution
workflow.add_edge(START, "pop_task")

workflow.add_conditional_edges(
    "pop_task",
    _is_queue_empty,
    {
        "END": END,
        "push_to_github": "push_to_github",
        "write_ui_code": "write_ui_code"
    }
)

workflow.add_edge("push_to_github", END)

workflow.add_edge("write_ui_code", "lint_code")

workflow.add_conditional_edges(
    "lint_code",
    _did_linter_pass,
    {"write_ui_code": "write_ui_code", "run_tests": "run_tests"}
)

workflow.add_conditional_edges(
    "run_tests",
    _did_tests_pass,
    {"write_ui_code": "write_ui_code", "browser_check": "browser_check"}
)

workflow.add_conditional_edges(
    "browser_check",
    _is_console_clean,
    {"write_ui_code": "write_ui_code", "mark_task_complete": "mark_task_complete"}
)
workflow.add_edge("mark_task_complete", "pop_task")

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

frontend_dev_subgraph = workflow.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    from langchain_core.runnables import RunnableConfig
    import uuid
    
    print("Starting Frontend Developer Agent...\n")
    
    # Mock global state
    initial_state = {
        "final_design_doc": "Build a Next.js 14 dashboard with App Router. Pages: /dashboard (overview with stats cards), /dashboard/projects (project list with CRUD). Use Tailwind CSS for styling. Dark mode by default.",
        "workflow_tasks": [
            {"id": 1, "title": "Create the main dashboard layout and navigation sidebar"},
            {"id": 2, "title": "Build the projects list page with a data table"}
        ],
        "current_task": None,
        "iteration_count": 0
    }
    
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid.uuid4())}}
    
    for event in frontend_dev_subgraph.stream(initial_state, config=config):
        for node_name, state_update in event.items():
            print(f"\n--- Node: {node_name} ---")
    
    print("\nFrontend Developer finished.")
