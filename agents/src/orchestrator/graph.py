from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from agents.src.orchestrator.state import WorkflowState

# Import all compiled subgraphs
from agents.src.agents.planning.graph import planning_subgraph
from agents.src.agents.product_manager.graph import pm_phase_a_subgraph, pm_phase_b_subgraph
from agents.src.agents.architect.graph import architect_subgraph
from agents.src.agents.task_breakdown.graph import task_breakdown_subgraph
from agents.src.agents.database_engineer.graph import database_engineer_subgraph
from agents.src.agents.backend_dev.graph import backend_dev_subgraph
from agents.src.agents.frontend_dev.graph import frontend_dev_subgraph
from agents.src.agents.qa.graph import qa_subgraph
from agents.src.agents.reviewer.graph import reviewer_subgraph
from agents.src.agents.security.graph import security_subgraph
from agents.src.agents.devops.graph import devops_subgraph

# ===========================================================================
# SUBGRAPH EXECUTOR WITH INTERRUPT BUBBLING
# ===========================================================================

from langgraph.errors import GraphInterrupt

_subgraph_counters = {}

import asyncio
import os
from agents.src.shared.checkpointer import get_async_checkpointer

_SUBGRAPH_TIMEOUT = int(os.getenv("SUBGRAPH_TIMEOUT_SECONDS", "600"))

async def _stream_subgraph(bound_subgraph, stream_input, config, thread_id: str, print_subtask: bool = False):
    async def _consume():
        async for event in bound_subgraph.astream(stream_input, config=config):
            for sub_node, _ in event.items():
                if sub_node != "__interrupt__":
                    from backend.telemetry import broadcast_subgraph_node
                    broadcast_subgraph_node(sub_node, thread_id)
                    if print_subtask:
                        import time
                        print(f"      ↳ [{time.strftime('%H:%M:%S')}] Sub-task completed: {sub_node}")

    await asyncio.wait_for(_consume(), timeout=_SUBGRAPH_TIMEOUT)

async def _run_subgraph_with_interrupts(subgraph, initial_input, config):
    thread_id = config["configurable"]["thread_id"]
    if thread_id not in _subgraph_counters:
        _subgraph_counters[thread_id] = 0
        
    async with get_async_checkpointer("checkpoints.sqlite") as checkpointer:
        bound_subgraph = subgraph.builder.compile(checkpointer=checkpointer)

        # First, if the subgraph hasn't started at all, run it with initial_input.
        # We check sub_state.values to distinguish between "never started" (no values)
        # and "fully finished" (has values but no next nodes). A completed subgraph
        # must NOT be re-invoked, or it restarts the entire graph from the beginning.
        sub_state = await bound_subgraph.aget_state(config)
        already_has_state = bool(sub_state.values)
        if not already_has_state and not sub_state.next and not (sub_state.tasks and any(t.interrupts for t in sub_state.tasks)):
            await _stream_subgraph(bound_subgraph, initial_input, config, thread_id)
                
        local_count = 0
        # Process any interrupts in a loop
        while True:
            sub_state = await bound_subgraph.aget_state(config)
            has_sub_interrupts = False
            payload = "Awaiting approval"
            
            if sub_state.tasks:
                for task in sub_state.tasks:
                    if task.interrupts:
                        has_sub_interrupts = True
                        payload = task.interrupts[0].value
                        break
                        
            if not sub_state.next and not has_sub_interrupts:
                break  # Subgraph is completely finished
                
            # If the subgraph is paused at a user interaction node (like user_approval),
            # broadcast this node name to the UI so the active highlight moves to it.
            if has_sub_interrupts and sub_state.next:
                from backend.telemetry import broadcast_subgraph_node
                broadcast_subgraph_node(sub_state.next[0], thread_id)

                # Subgraph is paused at an interrupt. Bubble interrupt to parent.
                user_response = interrupt(payload)
                
                local_count += 1
                
                # If we have already streamed this interrupt to the subgraph in memory,
                # skip streaming to avoid breaking the state during LangGraph replays.
                if local_count <= _subgraph_counters[thread_id]:
                    continue
                    
                # We haven't streamed this one yet. Stream it!
                _subgraph_counters[thread_id] += 1
                
                # Resume the subgraph with the user's response
                await _stream_subgraph(bound_subgraph, Command(resume=user_response), config, thread_id, print_subtask=True)
            else:
                # has_sub_interrupts is False, but sub_state.next is True
                # This means the subgraph was interrupted by an error and needs to be retried
                await _stream_subgraph(bound_subgraph, None, config, thread_id, print_subtask=True)
                        
        final_state = await bound_subgraph.aget_state(config)
        return final_state.values

# ===========================================================================
# WRAPPER NODES (Passing state between subgraphs)
# ===========================================================================

async def planning_stage(state: WorkflowState) -> dict:
    out = await _run_subgraph_with_interrupts(
        planning_subgraph,
        {"user_req": state.user_req},
        {"configurable": {"thread_id": f"{state.workflowId}-planning"}}
    )
    updated_req = (out.get("user_req") if isinstance(out, dict) else None) or state.user_req
    return {"user_req": updated_req}

async def pm_phase_a_stage(state: WorkflowState) -> dict:
    out = await _run_subgraph_with_interrupts(
        pm_phase_a_subgraph,
        {"user_req": state.user_req},
        {"configurable": {"thread_id": f"{state.workflowId}-pm_a"}}
    )
    project_name = out.get("project_name", "")
    repo_name = project_name.lower().replace(" ", "-") if project_name else f"auto-sdlc-{state.workflowId[:6]}"
    return {
        "prd": out.get("prd", ""),
        "project_name": project_name,
        "github_repo_name": repo_name
    }

async def architect_stage(state: WorkflowState) -> dict:
    out = await _run_subgraph_with_interrupts(
        architect_subgraph,
        {
            "user_req": state.prd,
            "prd": state.prd,
            "project_name": state.project_name
        },
        {"configurable": {"thread_id": f"{state.workflowId}-architect"}}
    )
    return {
        "final_design_doc": out.get("final_design_doc", "")
    }

async def task_breakdown_stage(state: WorkflowState) -> dict:
    out = await _run_subgraph_with_interrupts(
        task_breakdown_subgraph,
        {
            "prd": state.prd,
            "final_design_doc": state.final_design_doc,
            "project_name": state.project_name
        },
        {"configurable": {"thread_id": f"{state.workflowId}-task_breakdown"}}
    )
    workflow_tasks = out.get("workflow_tasks", [])
    
    import json
    try:
        with open("tasks-proj.json", "w", encoding="utf-8") as f:
            json.dump(workflow_tasks, f, indent=4)
    except Exception as e:
        with open("debug_tasks.txt", "w") as f:
            f.write(str(e))

    return {
        "workflow_tasks": workflow_tasks,
        "active_tasks": workflow_tasks,
        "completed_task_titles": []
    }

async def pm_phase_b_stage(state: WorkflowState) -> dict:
    await _run_subgraph_with_interrupts(
        pm_phase_b_subgraph,
        {
            "workflow_tasks": state.workflow_tasks,
            "user_req": state.user_req,
            "prd": state.prd,
            "project_name": state.project_name
        },
        {"configurable": {"thread_id": f"{state.workflowId}-pm_b"}}
    )
    return {}

# ===========================================================================
# DISPATCHER LOOP & WRAPPERS
# ===========================================================================

MAX_DISPATCHER_ITERATIONS = 50

def dispatcher_stage(state: WorkflowState) -> dict:
    """
    Evaluates dependencies and priority, picks the next agent role to execute,
    and queues up their ready tasks.
    """
    import time as _time
    wf_id = state.workflowId

    # ── Safety guard: max iteration count (persisted in WorkflowState) ─────
    iteration = state.dispatcher_iteration_count + 1

    if iteration > MAX_DISPATCHER_ITERATIONS:
        print(f"[SAFETY][{_time.strftime('%H:%M:%S')}] Dispatcher exceeded {MAX_DISPATCHER_ITERATIONS} iterations for workflow {wf_id}. Forcing END.")
        return {"active_role": "", "active_tasks": [], "dispatcher_iteration_count": iteration}

    all_tasks = state.workflow_tasks
    completed = set(state.completed_task_titles)

    print(f"[DISPATCHER][{_time.strftime('%H:%M:%S')}] Iteration {iteration} | Total tasks: {len(all_tasks)} | Completed: {len(completed)}")
    
    # 1. Find all pending tasks whose dependencies are fully met
    ready_tasks = []
    for t in all_tasks:
        title = t.get("title", "")
        if title in completed:
            continue
            
        deps = t.get("dependencies", [])
        if all(dep in completed for dep in deps):
            ready_tasks.append(t)
            
    if not ready_tasks:
        # Either all tasks are done, or there's an unresolvable dependency cycle
        print(f"[DISPATCHER][{_time.strftime('%H:%M:%S')}] No ready tasks remaining. Ending workflow.")
        return {"active_role": "", "active_tasks": [], "dispatcher_iteration_count": iteration}
        
    # 2. Tie-breaker precedence
    precedence = ["database_engineer", "devops", "backend", "frontend", "qa", "reviewer", "security"]
    def get_precedence(role: str) -> int:
        return precedence.index(role) if role in precedence else 99
        
    # 3. Sort by priority (1 is highest), then by precedence
    ready_tasks.sort(key=lambda x: (x.get("priority", 5), get_precedence(x.get("assignee_role", ""))))
    
    # 4. Group ready tasks by role; if multiple independent roles are ready, run in parallel
    grouped: dict[str, list[dict]] = {}
    for t in ready_tasks:
        r = t.get("assignee_role", "") or "backend"
        grouped.setdefault(r, []).append(t)

    # Gate/verification roles (qa, reviewer, security) run sequentially after build tasks
    _SERIAL_ROLES = {"qa", "reviewer", "security"}
    concurrent_roles = [r for r in grouped if r not in _SERIAL_ROLES]

    # Sequential execution in a single workspace avoids .git lock collisions and API 429 bursts.
    # Parallel batching can be opted in via SDLC_ENABLE_PARALLEL_BATCH=1.
    if os.getenv("SDLC_ENABLE_PARALLEL_BATCH") == "1" and len(concurrent_roles) > 1:
        parallel_map = {r: grouped[r] for r in concurrent_roles}
        dispatch_key = "PARALLEL::" + "|".join(
            f"{r}:{','.join(sorted(t.get('title', '') for t in tasks))}"
            for r, tasks in sorted(parallel_map.items())
        )
        if state.dispatcher_last_dispatch == dispatch_key:
            print(f"[SAFETY][{_time.strftime('%H:%M:%S')}] Dispatcher would re-dispatch identical parallel batch. Forcing END.")
            return {"active_role": "", "active_tasks": [], "parallel_tasks_by_role": {}, "dispatcher_iteration_count": iteration}
        print(f"[DISPATCHER][{_time.strftime('%H:%M:%S')}] Dispatching PARALLEL batch for roles={list(parallel_map.keys())}")
        return {
            "active_role": "parallel_batch",
            "active_tasks": [t for tasks in parallel_map.values() for t in tasks],
            "parallel_tasks_by_role": parallel_map,
            "dispatcher_iteration_count": iteration,
            "dispatcher_last_dispatch": dispatch_key,
        }

    # Single role dispatch
    chosen_role = ready_tasks[0].get("assignee_role", "") or "backend"
    tasks_for_role = grouped[chosen_role]

    # ── Safety guard: detect identical re-dispatch (persisted in WorkflowState) ─
    dispatch_key = f"{chosen_role}::{'|'.join(sorted(t.get('title', '') for t in tasks_for_role))}"
    if state.dispatcher_last_dispatch == dispatch_key:
        print(f"[SAFETY][{_time.strftime('%H:%M:%S')}] Dispatcher would re-dispatch identical work: {dispatch_key}. Forcing END to break loop.")
        return {"active_role": "", "active_tasks": [], "parallel_tasks_by_role": {}, "dispatcher_iteration_count": iteration}

    print(f"[DISPATCHER][{_time.strftime('%H:%M:%S')}] Dispatching role='{chosen_role}' with {len(tasks_for_role)} task(s): {[t.get('title','') for t in tasks_for_role]}")
    
    return {
        "active_role": chosen_role,
        "active_tasks": tasks_for_role,
        "parallel_tasks_by_role": {},
        "dispatcher_iteration_count": iteration,
        "dispatcher_last_dispatch": dispatch_key,
    }

def _dispatcher_router(state: WorkflowState) -> str:
    """Routes execution to the active agent."""
    role = state.active_role
    if not role:
        return END
        
    if role == "parallel_batch":
        return "parallel_batch_stage"
    if role == "backend":
        return "backend_dev_stage"
    if role == "frontend":
        return "frontend_dev_stage"
        
    # Strictly prevent routing back to setup phases (planning, architect, etc)
    # which causes the orchestrator to loop and restart graph executions.
    valid_stages = {
        "database_engineer_stage", "devops_stage", "backend_dev_stage", 
        "frontend_dev_stage", "qa_stage", "reviewer_stage", "security_stage"
    }
    
    target_stage = f"{role}_stage"
    if target_stage not in valid_stages:
        print(f"Warning: Invalid assignee_role '{role}'. Defaulting to 'backend_dev_stage'.")
        return "backend_dev_stage"
        
    return target_stage

# ---------------------------------------------------------------------------
# AGENT WRAPPER STAGES
# ---------------------------------------------------------------------------

# Counter to generate unique thread IDs for each subgraph invocation
_subgraph_batch_counter: dict = {}

async def _execute_agent_subgraph(state: WorkflowState, subgraph, role_name: str) -> dict:
    import hashlib
    import time as _time

    # ── Generate a UNIQUE thread_id per task batch ─────────────────────────
    # This prevents checkpoint collision: each batch of tasks gets a fresh
    # checkpoint so the subgraph actually processes new work instead of
    # returning stale results from a previous run.
    task_titles = sorted(t.get("title", "") for t in state.active_tasks)
    batch_hash = hashlib.md5("::".join(task_titles).encode()).hexdigest()[:8]
    unique_thread_id = f"{state.workflowId}-{role_name}-{batch_hash}"

    print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] Executing {role_name} with thread_id='{unique_thread_id}' for tasks: {task_titles}")

    from agents.src.shared.workspace import count_source_files
    _CODE_WRITERS = {"backend", "frontend"}
    _CODE_CONSUMERS = {"qa", "reviewer", "security"}
    no_code_rejection = False

    # QA / Reviewer / Security have nothing to verify on an empty project: skip them
    # instead of burning LLM turns and falsely approving.
    if role_name in _CODE_CONSUMERS and count_source_files() == 0:
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} SKIPPED: workspace has no source code files to verify.")
        return {
            "completed_task_titles": state.completed_task_titles.copy(),
            "workflow_tasks": state.workflow_tasks.copy(),
            "active_role": "",
            "active_tasks": [],
            "active_pr_number": state.active_pr_number,
        }

    subgraph_input = {
        "project_name": state.project_name if state.project_name else state.projectId,
        "prd": state.prd,
        "final_design_doc": state.final_design_doc,
        "source_code_paths": ["/backend", "/frontend"],
        "workflow_tasks": state.active_tasks,
        "active_pr_number": state.active_pr_number,
        "github_repo_name": state.github_repo_name
    }

    async def _safe_run(sg, inp, cfg):
        """Runs a subgraph; a timeout is reported instead of crashing the whole pipeline."""
        try:
            return await _run_subgraph_with_interrupts(sg, inp, cfg)
        except TimeoutError:
            print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} TIMED OUT after {_SUBGRAPH_TIMEOUT}s.")
            return {"__timeout__": True}

    # Send only active_tasks to the sub-agent
    out = await _safe_run(
        subgraph,
        subgraph_input,
        {"configurable": {"thread_id": unique_thread_id}}
    )
    timed_out = bool(out.get("__timeout__"))

    # ── No-code gate: developers must leave real source files on disk ──────
    if role_name in _CODE_WRITERS and not timed_out and count_source_files() == 0:
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} produced NO source files (only folders/docs). Retrying once...")
        out = await _safe_run(
            subgraph,
            subgraph_input,
            {"configurable": {"thread_id": f"{unique_thread_id}-retry"}}
        )
        timed_out = bool(out.get("__timeout__"))
        if count_source_files() == 0:
            no_code_rejection = True
            print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} still produced no source files after retry. Task will NOT be marked complete.")

    # A timed-out developer did not finish its work -> reject. A timed-out verification
    # gate (qa/reviewer/security) is infrastructure trouble, so it is skipped with a warning.
    if timed_out and role_name in _CODE_WRITERS:
        no_code_rejection = True
    if timed_out and role_name in _CODE_CONSUMERS:
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} timed out; continuing without its verdict.")
    
    new_completed = state.completed_task_titles.copy()
    new_global_tasks = state.workflow_tasks.copy()
    active_pr_number = state.active_pr_number
    
    # Check if the agent rejected the work (e.g. reviewer failed)
    # If the sub-agent outputs `code_review_approved: False` or `all_tests_passed: False`, we don't complete the task
    is_rejected = no_code_rejection
    if "code_review_approved" in out and not out["code_review_approved"]:
        is_rejected = True
    if "all_tests_passed" in out and not out["all_tests_passed"]:
        is_rejected = True
    if "security_approved" in out and not out["security_approved"]:
        is_rejected = True
        
    if not is_rejected:
        # Mark tasks as completed
        for t in state.active_tasks:
            title = t.get("title", "")
            if title not in new_completed:  # Prevent duplicate entries
                new_completed.append(title)
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} APPROVED. Completed: {[t.get('title','') for t in state.active_tasks]}")
    else:
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} REJECTED. Tasks NOT marked complete.")
            
    # Pull any newly spawned tasks (e.g., bug fixes, PR revisions)
    new_tasks = out.get("new_workflow_tasks") if isinstance(out, dict) else None
    if isinstance(new_tasks, list) and new_tasks:
        new_global_tasks.extend(new_tasks)
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} spawned {len(new_tasks)} new task(s).")
        
    # Capture PR number if Developer agents created one
    if "active_pr_number" in out and out["active_pr_number"]:
        active_pr_number = out["active_pr_number"]
        
    return {
        "completed_task_titles": new_completed,
        "workflow_tasks": new_global_tasks,
        "active_role": "",
        "active_tasks": [],
        "active_pr_number": active_pr_number
    }

async def database_engineer_stage(state: WorkflowState) -> dict:
    return await _execute_agent_subgraph(state, database_engineer_subgraph, "database_engineer")

async def devops_stage(state: WorkflowState) -> dict:
    return await _execute_agent_subgraph(state, devops_subgraph, "devops")

async def backend_dev_stage(state: WorkflowState) -> dict:
    return await _execute_agent_subgraph(state, backend_dev_subgraph, "backend")

async def frontend_dev_stage(state: WorkflowState) -> dict:
    return await _execute_agent_subgraph(state, frontend_dev_subgraph, "frontend")

async def qa_stage(state: WorkflowState) -> dict:
    return await _execute_agent_subgraph(state, qa_subgraph, "qa")

async def reviewer_stage(state: WorkflowState) -> dict:
    return await _execute_agent_subgraph(state, reviewer_subgraph, "reviewer")

async def security_stage(state: WorkflowState) -> dict:
    return await _execute_agent_subgraph(state, security_subgraph, "security")

async def parallel_batch_stage(state: WorkflowState) -> dict:
    """Executes multiple independent role subgraphs concurrently via asyncio.gather."""
    import asyncio
    role_to_subgraph = {
        "database_engineer": database_engineer_subgraph,
        "devops": devops_subgraph,
        "backend": backend_dev_subgraph,
        "frontend": frontend_dev_subgraph,
    }
    batches = state.parallel_tasks_by_role or {}
    if not batches:
        return {"active_role": "", "active_tasks": [], "parallel_tasks_by_role": {}}

    async def _run_role(role_name: str, tasks: list[dict]):
        sub = role_to_subgraph.get(role_name, backend_dev_subgraph)
        sub_state = state.model_copy(update={"active_tasks": tasks, "active_role": role_name})
        return await _execute_agent_subgraph(sub_state, sub, role_name)

    results = await asyncio.gather(
        *[_run_role(r, t) for r, t in batches.items()],
        return_exceptions=True,
    )

    merged_completed = list(state.completed_task_titles)
    merged_tasks = list(state.workflow_tasks)
    known_titles = {t.get("title", "") for t in merged_tasks if isinstance(t, dict)}
    active_pr = state.active_pr_number

    for res in results:
        if isinstance(res, BaseException):
            print(f"[PARALLEL_BATCH] Subgraph error: {res}")
            continue
        if not isinstance(res, dict):
            continue
        for title in res.get("completed_task_titles", []):
            if title not in merged_completed:
                merged_completed.append(title)
        for t in res.get("workflow_tasks", []):
            if isinstance(t, dict) and t.get("title", "") not in known_titles:
                merged_tasks.append(t)
                known_titles.add(t.get("title", ""))
        if res.get("active_pr_number"):
            active_pr = res["active_pr_number"]

    return {
        "completed_task_titles": merged_completed,
        "workflow_tasks": merged_tasks,
        "active_role": "",
        "active_tasks": [],
        "parallel_tasks_by_role": {},
        "active_pr_number": active_pr,
    }

# ===========================================================================
# PARENT GRAPH ASSEMBLY
# ===========================================================================

parent_workflow = StateGraph(WorkflowState)

# Setup Phase Nodes
parent_workflow.add_node("planning_stage", planning_stage)
parent_workflow.add_node("pm_phase_a_stage", pm_phase_a_stage)
parent_workflow.add_node("architect_stage", architect_stage)
parent_workflow.add_node("task_breakdown_stage", task_breakdown_stage)
parent_workflow.add_node("pm_phase_b_stage", pm_phase_b_stage)

# Dispatcher Loop Nodes
parent_workflow.add_node("dispatcher_stage", dispatcher_stage)
parent_workflow.add_node("database_engineer_stage", database_engineer_stage)
parent_workflow.add_node("devops_stage", devops_stage)
parent_workflow.add_node("backend_dev_stage", backend_dev_stage)
parent_workflow.add_node("frontend_dev_stage", frontend_dev_stage)
parent_workflow.add_node("qa_stage", qa_stage)
parent_workflow.add_node("reviewer_stage", reviewer_stage)
parent_workflow.add_node("security_stage", security_stage)
parent_workflow.add_node("parallel_batch_stage", parallel_batch_stage)

# ── Linear Setup Phase ──────────────────────────────────────────────────
parent_workflow.add_edge(START, "planning_stage")
parent_workflow.add_edge("planning_stage", "pm_phase_a_stage")
parent_workflow.add_edge("pm_phase_a_stage", "architect_stage")
parent_workflow.add_edge("architect_stage", "task_breakdown_stage")
parent_workflow.add_edge("task_breakdown_stage", "pm_phase_b_stage")
parent_workflow.add_edge("pm_phase_b_stage", "dispatcher_stage")

# ── Dispatcher Routing ──────────────────────────────────────────────────
parent_workflow.add_conditional_edges(
    "dispatcher_stage",
    _dispatcher_router,
    {
        "database_engineer_stage": "database_engineer_stage",
        "devops_stage": "devops_stage",
        "backend_dev_stage": "backend_dev_stage",
        "frontend_dev_stage": "frontend_dev_stage",
        "qa_stage": "qa_stage",
        "reviewer_stage": "reviewer_stage",
        "security_stage": "security_stage",
        "parallel_batch_stage": "parallel_batch_stage",
        END: END
    }
)

# ── Loop Back to Dispatcher ─────────────────────────────────────────────
parent_workflow.add_edge("database_engineer_stage", "dispatcher_stage")
parent_workflow.add_edge("devops_stage", "dispatcher_stage")
parent_workflow.add_edge("backend_dev_stage", "dispatcher_stage")
parent_workflow.add_edge("frontend_dev_stage", "dispatcher_stage")
parent_workflow.add_edge("qa_stage", "dispatcher_stage")
parent_workflow.add_edge("reviewer_stage", "dispatcher_stage")
parent_workflow.add_edge("security_stage", "dispatcher_stage")
parent_workflow.add_edge("parallel_batch_stage", "dispatcher_stage")

from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
orchestration_graph = parent_workflow.compile(checkpointer=checkpointer)
