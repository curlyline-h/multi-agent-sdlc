"""
Real Multi-Agent Orchestrator Execution for Benchmark Scenarios.
Executes the actual parent_workflow LangGraph orchestrator from agents.src.orchestrator.graph,
coordinating all 11 agents across planning, PRD, architecture, task breakdown,
dispatch, domain engineering, review, QA, security, and devops.
Auto-resumes human approval gates to execute headless end-to-end evaluation.
"""
import os
import sys
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Setup database & telemetry
from backend.database import AsyncSessionLocal
from backend.models import Project, Workflow, Task, AgentLogModel
from sqlalchemy import select
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from agents.src.orchestrator.graph import parent_workflow

ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_SPLIT_PATH = ROOT_DIR / "data" / "splits" / "test.json"
RESULTS_DIR = ROOT_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

async def execute_real_orchestrator_for_scenario(scenario: dict, project_id: int = 1):
    scen_id = scenario["id"]
    cat = scenario["category"]
    req = scenario["requirement"]
    thread_id = f"1-{scen_id}-{int(time.time())}"
    from backend.telemetry import set_active_project_id
    set_active_project_id(str(project_id))

    print(f"\n{'='*70}")
    print(f"RUNNING REAL ORCHESTRATOR FOR SCENARIO: {scen_id} [{cat.upper()}]")
    print(f"Requirement: {req}")
    print(f"{'='*70}")

    start_time = time.time()
    node_history = []

    async with AsyncSessionLocal() as db:
        # Create or fetch project
        proj = await db.get(Project, project_id)
        if not proj:
            proj = Project(
                id=project_id,
                title="SDLC Live Evaluation",
                description="Live multi-agent benchmark project",
                path=str(ROOT_DIR),
                current_status="ACTIVE",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(proj)
            await db.commit()

        # Create workflow entry
        stmt = select(Workflow).where(Workflow.project_id == project_id)
        wf = (await db.execute(stmt)).scalars().first()
        if not wf:
            wf = Workflow(
                project_id=project_id,
                current_state="START",
                status="RUNNING",
                source_branch="main",
                target_branch="main",
                next_agent="",
                summary=""
            )
            db.add(wf)
            await db.commit()
            await db.refresh(wf)
        else:
            wf.status = "RUNNING"
            wf.current_state = "START"
            await db.commit()

    async with AsyncSqliteSaver.from_conn_string("checkpoints_eval.sqlite") as checkpointer:
        await checkpointer.setup()
        orchestration_graph = parent_workflow.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        initial_input = {
            "user_req": req,
            "workflowId": thread_id,
            "projectId": str(project_id),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "prd": "",
            "project_name": "",
            "final_design_doc": "",
            "final_file_changes": [],
            "agent_logs": [],
            "human_interventions": [],
            "completed_task_titles": [],
            "workflow_tasks": [],
            "active_tasks": [],
            "github_repo_name": "",
        }

        current_input = initial_input
        max_turns = 40
        turns = 0

        while turns < max_turns:
            turns += 1
            print(f"\n--- [Turn {turns}] Streaming Orchestrator Graph ---")
            has_interrupt = False
            interrupt_val = None

            try:
                async for event in orchestration_graph.astream(current_input, config=config):
                    for node_name, state_update in event.items():
                        if node_name != "__interrupt__":
                            node_history.append(node_name)
                            timestamp = time.strftime('%H:%M:%S')
                            print(f"  [{timestamp}] Stage Executed: {node_name}")
                            if isinstance(state_update, dict):
                                if "prd" in state_update and state_update["prd"]:
                                    print(f"      -> PRD synthesized ({len(state_update['prd'].split())} words)")
                                if "final_design_doc" in state_update and state_update["final_design_doc"]:
                                    print(f"      -> Design doc synthesized ({len(state_update['final_design_doc'].split())} words)")
                                if "workflow_tasks" in state_update and state_update["workflow_tasks"]:
                                    print(f"      -> Workflow tasks updated ({len(state_update['workflow_tasks'])} total tasks)")
                                if "active_role" in state_update and state_update["active_role"]:
                                    print(f"      -> Dispatching active role: {state_update['active_role']}")
                                if "completed_task_titles" in state_update:
                                    print(f"      -> Completed tasks: {len(state_update['completed_task_titles'])}")
            except Exception as e:
                err_str = str(e)
                print(f"Exception during graph stream: {err_str}")
                if "429" in err_str or "rate_limit" in err_str.lower():
                    print("Rate limit reached. Sleeping 20s and retrying...")
                    time.sleep(20)
                    continue
                break

            # Inspect state after stream turn
            graph_state = await orchestration_graph.aget_state(config)

            # Check if there are pending interrupts
            if graph_state.tasks:
                for t in graph_state.tasks:
                    if hasattr(t, "interrupts") and t.interrupts:
                        has_interrupt = True
                        interrupt_val = t.interrupts[0].value
                        break

            if has_interrupt:
                int_type = interrupt_val.get("type") if isinstance(interrupt_val, dict) else ""
                print(f"  [INTERRUPT DETECTED] Type='{int_type}'")
                if int_type == "clarifying_questions":
                    ans = "Platform: Web (FastAPI + Next.js). Users: Support agents and customers. Database: PostgreSQL. CLEAR."
                    print(f"  Delivering Clarification Answer: '{ans}'")
                    current_input = Command(resume=ans)
                else:
                    print(f"  Auto-Approving Gate with: 'approve'")
                    current_input = Command(resume="approve")
                continue

            if not graph_state.next:
                print(f"\n[ORCHESTRATOR COMPLETE] Workflow finished naturally in {turns} turns!")
                break

            # If not interrupted and has next, run with None
            current_input = None

        final_state = await orchestration_graph.aget_state(config)
        elapsed = round(time.time() - start_time, 2)
        state_vals = final_state.values if hasattr(final_state, "values") else {}

        print(f"\n{'='*70}")
        print(f"EXECUTION SUMMARY FOR {scen_id}:")
        print(f"  Total Runtime: {elapsed} seconds across {turns} turns")
        print(f"  Unique Stages Visited ({len(set(node_history))}): {list(dict.fromkeys(node_history))}")
        print(f"  Tasks Created: {len(state_vals.get('workflow_tasks', []))}")
        print(f"  Tasks Completed: {len(state_vals.get('completed_task_titles', []))}")
        print(f"{'='*70}\n")

        res_dict = {
            "scenario_id": scen_id,
            "category": cat,
            "elapsed_seconds": elapsed,
            "turns": turns,
            "stages_visited": list(dict.fromkeys(node_history)),
            "prd": state_vals.get("prd", ""),
            "design_doc": state_vals.get("final_design_doc", ""),
            "workflow_tasks": state_vals.get("workflow_tasks", []),
            "completed_tasks": state_vals.get("completed_task_titles", []),
            "final_file_changes": state_vals.get("final_file_changes", []),
        }

        out_path = RESULTS_DIR / f"live_run_{scen_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(res_dict, f, indent=2)
        print(f"Results saved to {out_path}")

        return res_dict

if __name__ == "__main__":
    import sys
    with open(TEST_SPLIT_PATH, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    target_id = sys.argv[1] if len(sys.argv) > 1 else scenarios[0]["id"]
    scenario = next((s for s in scenarios if s["id"] == target_id), scenarios[0])
    asyncio.run(execute_real_orchestrator_for_scenario(scenario))
