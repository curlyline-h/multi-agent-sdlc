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

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async def _run_subgraph_with_interrupts(subgraph, initial_input, config):
    import asyncio
    from backend.websocket_manager import ws_manager
    from backend.telemetry import set_active_agent_role, effective_role_from_thread
    try:
        ws_manager.main_loop = asyncio.get_running_loop()
    except Exception:
        pass

    thread_id = config["configurable"]["thread_id"]
    role_for_thread = effective_role_from_thread(thread_id)
    if role_for_thread:
        set_active_agent_role(role_for_thread)
    if thread_id not in _subgraph_counters:
        _subgraph_counters[thread_id] = 0
        
    async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
        await checkpointer.setup()
        bound_subgraph = subgraph.builder.compile(checkpointer=checkpointer)

        # First, if the subgraph hasn't started at all, run it with initial_input.
        # We check sub_state.values to distinguish between "never started" (no values)
        # and "fully finished" (has values but no next nodes). A completed subgraph
        # must NOT be re-invoked, or it restarts the entire graph from the beginning.
        sub_state = await bound_subgraph.aget_state(config)
        already_has_state = bool(sub_state.values)
        if not already_has_state and not sub_state.next and not (sub_state.tasks and any(t.interrupts for t in sub_state.tasks)):
            async for event in bound_subgraph.astream(initial_input, config=config):
                for sub_node, _ in event.items():
                    if sub_node != "__interrupt__":
                        from backend.telemetry import broadcast_subgraph_node
                        broadcast_subgraph_node(sub_node, thread_id)
                
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
                async for event in bound_subgraph.astream(Command(resume=user_response), config=config):
                    for sub_node, _ in event.items():
                        if sub_node != "__interrupt__":
                            from backend.telemetry import broadcast_subgraph_node
                            broadcast_subgraph_node(sub_node, thread_id)
                            import time
                            print(f"      ↳ [{time.strftime('%H:%M:%S')}] Sub-task completed: {sub_node}")
            else:
                # has_sub_interrupts is False, but sub_state.next is True
                # This means the subgraph was interrupted by an error and needs to be retried
                async for event in bound_subgraph.astream(None, config=config):
                    for sub_node, _ in event.items():
                        if sub_node != "__interrupt__":
                            from backend.telemetry import broadcast_subgraph_node
                            broadcast_subgraph_node(sub_node, thread_id)
                            import time
                            print(f"      ↳ [{time.strftime('%H:%M:%S')}] Sub-task completed: {sub_node}")
                        
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
    effective_prd = state.prd if (state.prd and len(state.prd.strip()) > 50) else state.user_req
    out = await _run_subgraph_with_interrupts(
        architect_subgraph,
        {
            "user_req": state.user_req or effective_prd,
            "prd": effective_prd,
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
    from pathlib import Path
    try:
        with open("tasks-proj.json", "w", encoding="utf-8") as f:
            json.dump(workflow_tasks, f, indent=4)
        from agents.src.shared.tools import get_output_dir
        docs_dir = get_output_dir() / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "04_task_breakdown.json").write_text(json.dumps(workflow_tasks, indent=2), encoding="utf-8")
        md_lines = [
            f"# Task Breakdown & Topological DAG ({state.project_name or state.projectId})",
            "",
            "| # | Task ID | Role | Priority | Summary | Dependencies |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for idx, t in enumerate(workflow_tasks):
            deps = ", ".join(t.get("dependencies", [])) or "None"
            md_lines.append(
                f"| {idx+1} | `{t.get('id', f'task-{idx+1}')}` | `{t.get('assignee_role', '')}` | "
                f"{t.get('priority', 3)} | **{t.get('title', '')}** — {t.get('description', '')[:120]} | {deps} |"
            )
        (docs_dir / "04_task_breakdown.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    except Exception as e:
        with open("debug_tasks.txt", "w") as f:
            f.write(str(e))

    try:
        from backend.telemetry import sync_workflow_tasks_to_db
        await sync_workflow_tasks_to_db(state.projectId, workflow_tasks, [])
    except Exception as e:
        print(f"[DB SYNC] Warning: could not sync initial tasks to DB: {e}")

    return {
        "workflow_tasks": workflow_tasks,
        "active_tasks": workflow_tasks,
        "completed_task_titles": []
    }

async def pm_phase_b_stage(state: WorkflowState) -> dict:
    out = await _run_subgraph_with_interrupts(
        pm_phase_b_subgraph,
        {
            "workflow_tasks": state.workflow_tasks,
            "user_req": state.user_req,
            "prd": state.prd,
            "project_name": state.project_name
        },
        {"configurable": {"thread_id": f"{state.workflowId}-pm_b"}}
    )
    jira_epic_key = out.get("jira_epic_key", "") if isinstance(out, dict) else ""
    jira_ticket_keys = out.get("jira_ticket_keys", []) if isinstance(out, dict) else []

    # Enrich workflow_tasks with Jira keys (SCRUM-XX) and create GitHub Issues (#N) for issue-driven execution
    enriched_tasks = list(state.workflow_tasks)
    try:
        from agents.src.shared.issue_tracker import ensure_github_repo_and_issues
        enriched_tasks = ensure_github_repo_and_issues(
            state.github_repo_name, enriched_tasks, jira_epic_key=jira_epic_key
        )
        from backend.telemetry import sync_workflow_tasks_to_db
        await sync_workflow_tasks_to_db(state.projectId, enriched_tasks, state.completed_task_titles)
    except Exception as e:
        print(f"[IssueTracker] Warning enriching issues in pm_phase_b_stage: {e}")

    return {
        "workflow_tasks": enriched_tasks,
        "jira_epic_key": jira_epic_key,
        "jira_ticket_keys": jira_ticket_keys,
    }

# ===========================================================================
# DISPATCHER LOOP & WRAPPERS
# ===========================================================================

# Safety counters to prevent infinite loops (keyed by workflow ID)
_dispatcher_iteration_count: dict = {}
_dispatcher_last_dispatch: dict = {}
MAX_DISPATCHER_ITERATIONS = 50

def _norm(x: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]", "", str(x).lower())


def _dep_satisfied(dep, completed: set, all_tasks: list) -> bool:
    """A dependency is satisfied if it matches a completed title/id (case-insensitive),
    or if it matches no known task at all (unresolvable references must not block forever)."""
    if dep in completed:
        return True
    nd = _norm(dep)
    known = False
    for t in all_tasks:
        if nd in (_norm(t.get("title", "")), _norm(t.get("id", ""))):
            known = True
            if t.get("title", "") in completed:
                return True
    if not known:
        print(f"[DISPATCHER] Unknown dependency {dep!r}; treating as satisfied.")
        return True
    return False


def dispatcher_stage(state: WorkflowState) -> dict:
    """
    Evaluates dependencies and priority, picks the next agent role to execute,
    and queues up their ready tasks.
    """
    import time as _time
    wf_id = state.workflowId

    # ── Safety guard: max iteration count ──────────────────────────────────
    _dispatcher_iteration_count.setdefault(wf_id, 0)
    _dispatcher_iteration_count[wf_id] += 1
    iteration = _dispatcher_iteration_count[wf_id]

    if iteration > MAX_DISPATCHER_ITERATIONS:
        print(f"[SAFETY][{_time.strftime('%H:%M:%S')}] Dispatcher exceeded {MAX_DISPATCHER_ITERATIONS} iterations for workflow {wf_id}. Forcing END.")
        return {"active_role": "", "active_tasks": []}

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
        if all(_dep_satisfied(dep, completed, all_tasks) for dep in deps):
            ready_tasks.append(t)
            
    if not ready_tasks:
        pending = [t.get("title", "") for t in all_tasks if t.get("title", "") not in completed]
        if pending:
            print(f"[DISPATCHER][ERROR] No ready tasks but {len(pending)} pending (dependency cycle?): {pending}")
        # Either all tasks are done, or there's an unresolvable dependency cycle
        print(f"[DISPATCHER][{_time.strftime('%H:%M:%S')}] No ready tasks remaining. Ending workflow.")
        return {"active_role": "", "active_tasks": []}
        
    # 2. Tie-breaker precedence
    precedence = ["database_engineer", "devops", "backend", "frontend", "qa", "reviewer", "security"]
    def get_precedence(role: str) -> int:
        return precedence.index(role) if role in precedence else 99
        
    # 3. Sort by priority (1 is highest), then by precedence
    ready_tasks.sort(key=lambda x: (x.get("priority", 5), get_precedence(x.get("assignee_role", ""))))
    
    # 4. Pick the role of the most important ready task
    chosen_role = ready_tasks[0].get("assignee_role", "")
    
    # 5. Gather ALL ready tasks for that chosen role
    tasks_for_role = [t for t in ready_tasks if t.get("assignee_role", "") == chosen_role]

    # ── Safety guard: detect identical re-dispatch (same role + same tasks) ─
    dispatch_key = f"{chosen_role}::{'|'.join(sorted(t.get('title', '') for t in tasks_for_role))}"
    if _dispatcher_last_dispatch.get(wf_id) == dispatch_key:
        print(f"[SAFETY][{_time.strftime('%H:%M:%S')}] Dispatcher would re-dispatch identical work: {dispatch_key}. Forcing END to break loop.")
        return {"active_role": "", "active_tasks": []}
    _dispatcher_last_dispatch[wf_id] = dispatch_key

    print(f"[DISPATCHER][{_time.strftime('%H:%M:%S')}] Dispatching role='{chosen_role}' with {len(tasks_for_role)} task(s): {[t.get('title','') for t in tasks_for_role]}")
    
    return {"active_role": chosen_role, "active_tasks": tasks_for_role}

def _dispatcher_router(state: WorkflowState) -> str:
    """Routes execution to the active agent."""
    role = state.active_role
    if not role:
        return END
        
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
    base_thread_id = f"{state.workflowId}-{role_name}-{batch_hash}"
    attempt = _subgraph_batch_counter.get(base_thread_id, 0)
    _subgraph_batch_counter[base_thread_id] = attempt + 1
    # A retried batch needs a fresh checkpoint, otherwise the finished one returns stale output
    unique_thread_id = base_thread_id if attempt == 0 else f"{base_thread_id}-retry{attempt}"

    print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] Executing {role_name} with thread_id='{unique_thread_id}' for tasks: {task_titles}")

    # ── Claim Issue(s) on Jira (In Progress) & GitHub Issues (#N) ─────────
    try:
        from agents.src.shared.issue_tracker import transition_and_comment_on_claim
        transition_and_comment_on_claim(state.github_repo_name, state.active_tasks, role_name)
    except Exception as e:
        print(f"[IssueTracker] Claim hook warning: {e}")

    # Send only active_tasks to the sub-agent
    out = await _run_subgraph_with_interrupts(
        subgraph,
        {
            "project_name": state.project_name if state.project_name else state.projectId,
            "prd": state.prd,
            "final_design_doc": state.final_design_doc,
            "source_code_paths": ["/backend", "/frontend"],
            "workflow_tasks": state.active_tasks,
            "active_pr_number": state.active_pr_number,
            "github_repo_name": state.github_repo_name
        },
        {"configurable": {"thread_id": unique_thread_id}}
    )
    
    new_completed = state.completed_task_titles.copy()
    new_global_tasks = state.workflow_tasks.copy()
    active_pr_number = state.active_pr_number
    
    # Check if the agent rejected the work (e.g. reviewer failed)
    # If the sub-agent outputs `code_review_approved: False` or `all_tests_passed: False`, we don't complete the task
    # UNLESS we already spawned a remediation round for this gate, to guarantee bounded convergence.
    _gate_prefix = {"qa": "task-bugfix-", "reviewer": "task-review-", "security": "task-sec-"}.get(role_name)
    already_remediated = bool(_gate_prefix) and any(
        str(t.get("id", "")).startswith(_gate_prefix) for t in state.workflow_tasks
    )
    is_rejected = False
    if not already_remediated:
        if "code_review_approved" in out and not out["code_review_approved"]:
            is_rejected = True
        if "all_tests_passed" in out and not out["all_tests_passed"]:
            is_rejected = True
        if "security_approved" in out and not out["security_approved"]:
            is_rejected = True
        
    spawned_preview = (out.get("new_workflow_tasks") or []) if (not already_remediated and isinstance(out, dict)) else []
    if is_rejected and not spawned_preview:
        # Rejected with no remediation task: re-dispatching the identical batch would trip the loop guard
        # and END the whole workflow, abandoning other pending tasks. Close it out, loudly.
        print(f"[SUBGRAPH][WARNING] {role_name} rejected work but spawned no remediation task; closing batch as UNRESOLVED.")
        is_rejected = False
    if not is_rejected:
        # Mark tasks as completed
        for t in state.active_tasks:
            title = t.get("title", "")
            if title not in new_completed:  # Prevent duplicate entries
                new_completed.append(title)
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} APPROVED. Completed: {[t.get('title','') for t in state.active_tasks]}")
    else:
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} REJECTED (spawning remediation round). Tasks NOT marked complete yet.")
            
    # Pull any newly spawned tasks (e.g., bug fixes, PR revisions) only if not already remediated
    if not already_remediated and "new_workflow_tasks" in out and out["new_workflow_tasks"]:
        # Cap spawned tasks to at most 3 per gate to prevent exponential fan-out
        spawned = out["new_workflow_tasks"][:3]
        new_global_tasks.extend(spawned)
        print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name} spawned {len(spawned)} remediation task(s).")
        
    # Tasks that still failed lint/tests after all retries get ONE targeted fix task (never a fix of a fix)
    if isinstance(out, dict) and out.get("failed_tasks"):
        import hashlib as _hl
        for ft in out["failed_tasks"]:
            orig = ft.get("title", "")
            if not orig or orig.startswith("Fix: "):
                continue
            fix_id = "task-fix-" + _hl.md5(orig.encode()).hexdigest()[:6]
            if any(t.get("id") == fix_id for t in new_global_tasks):
                continue
            role_of = (state.active_tasks[0].get("assignee_role", "backend") if state.active_tasks else "backend")
            new_global_tasks.append({
                "id": fix_id,
                "title": f"Fix: {orig}",
                "description": f"The previous attempt for '{orig}' still failed checks. Fix the code so lint/tests pass. Errors:\n{ft.get('errors', '')}",
                "assignee_role": role_of,
                "priority": 1,
                "dependencies": [],
            })
            print(f"[SUBGRAPH][{_time.strftime('%H:%M:%S')}] {role_name}: '{orig}' still failing; queued fix task {fix_id}.")

    # Capture PR number if Developer agents created one
    if "active_pr_number" in out and out["active_pr_number"]:
        active_pr_number = out["active_pr_number"]

    # ── Update Jira Tickets (Done) & Close GitHub Issues (#N) ──────────────
    try:
        from agents.src.shared.issue_tracker import finalize_issues_after_subgraph
        finalize_issues_after_subgraph(
            state.github_repo_name,
            role_name,
            state.active_tasks,
            is_rejected=is_rejected,
            pr_number=active_pr_number,
        )
    except Exception as e:
        print(f"[IssueTracker] Finalize hook warning: {e}")

    try:
        from backend.telemetry import sync_workflow_tasks_to_db
        await sync_workflow_tasks_to_db(state.projectId, new_global_tasks, new_completed)
    except Exception as e:
        print(f"[DB SYNC] Warning: could not sync tasks to DB after {role_name}: {e}")
        
    return {
        "completed_task_titles": new_completed,
        "workflow_tasks": new_global_tasks,
        "active_role": "",
        "active_tasks": [],
        "active_pr_number": active_pr_number,
        "qa_passed": out.get("all_tests_passed", state.qa_passed),
        "reviewer_approved": out.get("code_review_approved", state.reviewer_approved),
        "security_approved": out.get("security_approved", state.security_approved),
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

import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_db_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
checkpointer = SqliteSaver(_db_conn)
orchestration_graph = parent_workflow.compile(checkpointer=checkpointer)
