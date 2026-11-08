"""
Task Breakdown Agent — Subgraph Definition

Flow:
  START
    → generate_tasks
  END
"""
from dotenv import load_dotenv
load_dotenv()
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agents.src.agents.task_breakdown.state import TaskBreakdownState
from agents.src.agents.task_breakdown.nodes import generate_tasks_node

# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
workflow = StateGraph(TaskBreakdownState)

workflow.add_node("generate_tasks", generate_tasks_node)

workflow.add_edge(START, "generate_tasks")
workflow.add_edge("generate_tasks", END)

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)

task_breakdown_subgraph = workflow.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    import os
    import json
    config = {"configurable": {"thread_id": "test-task-breakdown-001"}}

    print("Starting Task Breakdown Agent...")
    
    workspace_root = os.path.join(os.path.dirname(__file__), "../../../../")
    
    # Load PRD
    prd_path = os.path.join(workspace_root, "final_prd.md")
    try:
        with open(prd_path, "r", encoding="utf-8") as f:
            prd_content = f.read()
    except FileNotFoundError:
        print("Warning: final_prd.md not found. Using empty string.")
        prd_content = ""
        
    # Load Design Doc
    design_path = os.path.join(workspace_root, "final_design.md")
    try:
        with open(design_path, "r", encoding="utf-8") as f:
            design_content = f.read()
    except FileNotFoundError:
        print("Warning: final_design.md not found. Using empty string.")
        design_content = ""
    
    print("Executing Task Breakdown...")
    res = task_breakdown_subgraph.invoke(
        {
            "prd": prd_content,
            "final_design_doc": design_content
        },
        config=config,
    )

    state = task_breakdown_subgraph.get_state(config)
    tasks = state.values.get("workflow_tasks", [])
    
    print("\nTask Breakdown Finished!")
    print(f"Generated {len(tasks)} tasks.")
    
    output_path = os.path.join(workspace_root, "tasks.json")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2)
        print(f"Tasks saved to {output_path}")
    except Exception as e:
        print(f"Failed to save tasks: {e}")
