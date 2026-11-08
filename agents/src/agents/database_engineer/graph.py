"""
Database Engineer Agent — Subgraph Definition

Flow:
  START
    → setup_db                 (creates isolated DB)
    → write_migrations         (translates design to ORM/migrations based on tech stack)
    → execute_migrations       (runs migration commands)
    → validate_schema          (diffs physical DB vs design doc)
    → [router: loop back to write_migrations if diff fails, else END]
"""
from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.src.agents.database_engineer.state import DatabaseEngineerState
from agents.src.agents.database_engineer.nodes import (
    setup_db_node,
    write_migrations_node,
    execute_migrations_node,
    validate_schema_node,
    pop_task_node,
    mark_task_complete_node,
    push_to_github_node
)

# ---------------------------------------------------------------------------
# Router: Is Queue Empty?
# ---------------------------------------------------------------------------
def _is_queue_empty(state: DatabaseEngineerState) -> str:
    return "END" if state.current_task is None else "setup_db"


# ---------------------------------------------------------------------------
# Router: Should we revise migrations?
# ---------------------------------------------------------------------------
def _should_revise_migrations(state: DatabaseEngineerState) -> str:
    """
    If validation failed or migrations crashed, and we haven't hit the limit,
    loop back to rewrite the migrations. Otherwise end.
    """
    max_iterations = 3
    if not state.db_schema_ready and state.iteration_count < max_iterations:
        return "write_migrations"
    return "push_to_github"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
workflow = StateGraph(DatabaseEngineerState)

# Register all nodes
workflow.add_node("pop_task", pop_task_node)
workflow.add_node("setup_db", setup_db_node)
workflow.add_node("write_migrations", write_migrations_node)
workflow.add_node("execute_migrations", execute_migrations_node)
workflow.add_node("validate_schema", validate_schema_node)
workflow.add_node("push_to_github", push_to_github_node)
workflow.add_node("mark_task_complete", mark_task_complete_node)

# Flow execution
workflow.add_edge(START, "pop_task")
workflow.add_conditional_edges("pop_task", _is_queue_empty, {"END": END, "setup_db": "setup_db"})
workflow.add_edge("setup_db", "write_migrations")
workflow.add_edge("write_migrations", "execute_migrations")
workflow.add_edge("execute_migrations", "validate_schema")

# Autonomous self-healing loop
workflow.add_conditional_edges(
    "validate_schema",
    _should_revise_migrations,
    {
        "write_migrations": "write_migrations",
        "push_to_github": "push_to_github"
    }
)
workflow.add_edge("push_to_github", "mark_task_complete")
workflow.add_edge("mark_task_complete", "pop_task")

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

database_engineer_subgraph = workflow.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    from langchain_core.runnables import RunnableConfig
    from pathlib import Path
    
    # Read the actual design doc for testing
    design_path = Path(__file__).resolve().parents[4] / "final_design.md"
    try:
        mock_design = design_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Could not find design doc at {design_path}")
        mock_design = "No design found."
    
    initial_state = DatabaseEngineerState(
        project_name="test_agentc_db",
        final_design_doc=mock_design,
        workflow_tasks=[{"task_id": "db_setup", "description": "Create schema"}],
    )
    
    config = RunnableConfig(configurable={"thread_id": "test_db_1"})
    
    print("Starting Database Engineer Agent...")
    for event in database_engineer_subgraph.stream(initial_state, config=config):
        for key, value in event.items():
            print(f"\\n--- Node: {key} ---")
            if "migration_logs" in value:
                print(f"Logs: {value['migration_logs']}")
            if "schema_diff_notes" in value:
                print(f"Validation: {value['schema_diff_notes']}")
    
    print("\\nDatabase Engineer finished.")
