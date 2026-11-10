import datetime
import logging
import concurrent.futures
import contextvars
from backend.websocket_manager import ws_manager

logger = logging.getLogger("telemetry")

# LangChain uses ThreadPoolExecutor for synchronous nodes, which natively drops contextvars.
# We monkeypatch it globally here so that CURRENT_PROJECT_ID survives in background agents.
_original_submit = concurrent.futures.ThreadPoolExecutor.submit

def _context_preserving_submit(self, fn, *args, **kwargs):
    ctx = contextvars.copy_context()
    def wrapper():
        return ctx.run(fn, *args, **kwargs)
    return _original_submit(self, wrapper)

concurrent.futures.ThreadPoolExecutor.submit = _context_preserving_submit

# Context variable to hold active project_id and agent_role across threads
CURRENT_PROJECT_ID: contextvars.ContextVar[str] = contextvars.ContextVar("CURRENT_PROJECT_ID", default="")
CURRENT_AGENT_ROLE: contextvars.ContextVar[str] = contextvars.ContextVar("CURRENT_AGENT_ROLE", default="")
CURRENT_SCENARIO_ID: contextvars.ContextVar[str] = contextvars.ContextVar("CURRENT_SCENARIO_ID", default="")

_LIVE_EVENTS: list[str] = []
_STAGE_HISTORY: list[str] = []

def set_active_scenario_id(scenario_id: str, category: str = ""):
    CURRENT_SCENARIO_ID.set(f"{scenario_id} ({category})" if category else str(scenario_id))
    _LIVE_EVENTS.clear()
    _STAGE_HISTORY.clear()
    _write_live_progress_md(active_stage="initializing", active_agent="orchestrator", sub_node="START")

def _write_live_progress_md(active_stage: str = "", active_agent: str = "", sub_node: str = "", new_event: str = ""):
    try:
        from pathlib import Path
        import json as _json
        import time as _t
        root = Path(__file__).resolve().parents[1]
        ts = _t.strftime("%H:%M:%S")
        if new_event:
            _LIVE_EVENTS.append(f"- `[{ts}]` **{active_agent or 'agent'}**: {new_event}")
        if active_stage and active_stage not in _STAGE_HISTORY:
            _STAGE_HISTORY.append(active_stage)

        # Build Issue-Driven Board from tasks-proj.json and active scenario output directory
        from agents.src.shared.tools import get_output_dir
        scen_out = get_output_dir()
        tasks_list = []
        ib_path = scen_out / "issue_board.json"
        tp_path = root / "tasks-proj.json"
        jt_path = scen_out / "jira_tickets.json"
        gc_path = scen_out / "git_contributions.jsonl"

        jira_epic = "Pending"
        jira_keys = []
        if jt_path.exists():
            try:
                jd = _json.loads(jt_path.read_text(encoding="utf-8"))
                jira_epic = jd.get("epic_key", "Pending")
                jira_keys = jd.get("ticket_keys", [])
            except Exception:
                pass

        if ib_path.exists():
            try:
                ib = _json.loads(ib_path.read_text(encoding="utf-8"))
                tasks_list = ib.get("issues", [])
                jira_epic = ib.get("jira_epic_key") or jira_epic
            except Exception:
                pass
        elif tp_path.exists():
            try:
                tasks_list = _json.loads(tp_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        contribs_by_role = {}
        if gc_path.exists():
            try:
                for line in gc_path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        c = _json.loads(line)
                        r_lower = c.get("agent_name", "").lower()
                        contribs_by_role[r_lower] = c
            except Exception:
                pass

        issue_rows = []
        for idx, t in enumerate(tasks_list):
            jkey = t.get("jira_ticket_key") or (jira_keys[idx] if idx < len(jira_keys) else f"TASK-{idx+1}")
            gh_num = t.get("github_issue_number")
            issue_label = f"`{jkey}`" + (f" / `GH #{gh_num}`" if gh_num else "")
            role = t.get("assignee_role", "backend")
            title = t.get("title", "Task")
            deps = ", ".join(t.get("dependencies", [])) or "None"
            role_stage = f"{role}_stage" if role not in ("backend", "frontend") else f"{role}_dev_stage"

            # Determine status & contribution
            matched_c = None
            for cr_key, cr_val in contribs_by_role.items():
                if role in cr_key or (role == "backend" and "backend" in cr_key) or (role == "frontend" and "frontend" in cr_key):
                    matched_c = cr_val
            if active_stage == role_stage:
                status_badge = f"🔄 **IN PROGRESS** (`{sub_node}`)"
            elif role_stage in _STAGE_HISTORY:
                status_badge = "✅ **DONE**"
            else:
                status_badge = "⏳ `TODO`"

            contrib_cell = "—"
            if matched_c:
                sha = matched_c.get("commit_sha", "")[:7]
                pr = matched_c.get("pr_number", 0)
                pr_url = matched_c.get("pr_url", "")
                br = matched_c.get("branch_name", "")
                contrib_cell = f"`{sha}` on `{br}`" + (f" ([PR #{pr}]({pr_url}))" if pr_url else "")

            issue_rows.append(f"| {issue_label} | `{role}` | {title} | {deps[:45]} | {status_badge} | {contrib_cell} |")

        issue_table_md = (
            "| Issue (Jira / GitHub) | Assigned Agent | Issue Summary | Blocked By (DAG Deps) | Issue Status | Agent Git / PR Contribution |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            + ("\n".join(issue_rows) if issue_rows else "| *Generating issues in Phase 1...* | — | — | — | ⏳ | — |")
        )

        scen_label = CURRENT_SCENARIO_ID.get() or f"Project #{CURRENT_PROJECT_ID.get()}"
        recent = "\n".join(_LIVE_EVENTS[-35:]) if _LIVE_EVENTS else "- Waiting for events..."
        md = (
            f"# 🚀 Live Issue-Driven Multi-Agent SDLC Monitor\n\n"
            f"- **Active Scenario:** `{scen_label}`\n"
            f"- **Jira Parent Epic:** `{jira_epic}` (`https://hamzaabbasorax.atlassian.net/browse/{jira_epic}`)\n"
            f"- **Active Dispatcher Stage / Agent:** `{active_stage or 'running'}` / `{active_agent or 'orchestrator'}` (`{sub_node or '-'}`)\n"
            f"- **Last Updated:** `{ts}`\n\n"
            f"## 🎫 Live Issue Board & Agent Contributions (Hub-and-Spoke Dispatcher)\n"
            f"{issue_table_md}\n\n"
            f"## 🛠️ Real-Time Agent & Tool Activity Feed (Last 35 Events)\n{recent}\n"
        )
        (root / "LIVE_PROGRESS.md").write_text(md, encoding="utf-8")
    except Exception:
        pass

def set_active_project_id(project_id: str):
    """Sets the active project ID for the current thread execution context."""
    CURRENT_PROJECT_ID.set(str(project_id))

def get_active_project_id() -> str:
    """Gets the active project ID for the current thread execution context."""
    return CURRENT_PROJECT_ID.get()

def set_active_agent_role(role: str):
    """Sets the active agent role for the current execution context."""
    CURRENT_AGENT_ROLE.set(str(role))

def get_active_agent_role() -> str:
    """Gets the active agent role for the current execution context."""
    return CURRENT_AGENT_ROLE.get()

def _resolve_int_project_id(project_id: str):
    try:
        return int(project_id)
    except (ValueError, TypeError):
        try:
            # Extract leading integer if thread_id format like "12-scen_003"
            prefix = str(project_id).split("-")[0]
            return int(prefix)
        except (ValueError, TypeError):
            return None

async def _save_tool_log(project_id: str, tool_name: str, msg: str, agent_role: str = ""):
    from backend.database import AsyncSessionLocal
    from backend.models import AgentLogModel, Workflow
    from sqlalchemy import select
    p_id = _resolve_int_project_id(project_id)
    async with AsyncSessionLocal() as db:
        if p_id is not None:
            stmt = select(Workflow).where(Workflow.project_id == p_id)
        else:
            stmt = select(Workflow).order_by(Workflow.id.desc())
        wf = (await db.execute(stmt)).scalars().first()
        if wf:
            effective_role = agent_role or get_active_agent_role() or wf.next_agent or wf.current_state or "tool_execution"
            log_entry = AgentLogModel(
                workflow_id=wf.id,
                requesting_agent_id=effective_role,
                status="TOOL_CALL",
                request_details=msg,
                payload=tool_name,
                response=""
            )
            db.add(log_entry)
            await db.commit()

async def _save_terminal_log(project_id: str, payload_extra: dict, agent_role: str = ""):
    from backend.database import AsyncSessionLocal
    from backend.models import CommandExecution, Workflow
    from sqlalchemy import select
    p_id = _resolve_int_project_id(project_id)
    async with AsyncSessionLocal() as db:
        if p_id is not None:
            stmt = select(Workflow).where(Workflow.project_id == p_id)
        else:
            stmt = select(Workflow).order_by(Workflow.id.desc())
        wf = (await db.execute(stmt)).scalars().first()
        if wf and wf.project_id is not None:
            effective_role = agent_role or get_active_agent_role() or wf.next_agent or wf.current_state or "terminal"
            cmd = payload_extra.get("command", "")
            stdout = payload_extra.get("stdout", "")
            stderr = payload_extra.get("stderr", "")
            exit_code = payload_extra.get("exit_code", 0)
            cwd = payload_extra.get("cwd", "output")
            log_entry = CommandExecution(
                project_id=wf.project_id,
                agent_role=effective_role,
                command=cmd,
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code
            )
            db.add(log_entry)
            await db.commit()

async def _save_file_record(project_id: str, payload_extra: dict):
    from backend.database import AsyncSessionLocal
    from backend.models import FileRecord, Workflow
    from sqlalchemy import select
    p_id = _resolve_int_project_id(project_id)
    async with AsyncSessionLocal() as db:
        if p_id is not None:
            stmt = select(Workflow).where(Workflow.project_id == p_id)
        else:
            stmt = select(Workflow).order_by(Workflow.id.desc())
        wf = (await db.execute(stmt)).scalars().first()
        if wf and wf.project_id is not None:
            rec = FileRecord(
                project_id=wf.project_id,
                file_path=payload_extra.get("path", ""),
                action=payload_extra.get("action", "CREATED"),
                diff_snapshot=payload_extra.get("diff", ""),
                content_snapshot=payload_extra.get("content", "")[:4000] if payload_extra.get("content") else None,
            )
            db.add(rec)
            await db.commit()

async def sync_workflow_tasks_to_db(project_id: str, workflow_tasks: list, completed_titles: list = None):
    """Synchronizes LangGraph workflow_tasks into the PostgreSQL `tasks` and `agent_logs` tables."""
    import json as _json
    from backend.database import AsyncSessionLocal
    from backend.models import Task, Workflow
    from sqlalchemy import select, delete
    completed_set = set(completed_titles or [])
    p_id = _resolve_int_project_id(project_id)
    async with AsyncSessionLocal() as db:
        if p_id is not None:
            stmt = select(Workflow).where(Workflow.project_id == p_id)
        else:
            stmt = select(Workflow).order_by(Workflow.id.desc())
        wf = (await db.execute(stmt)).scalars().first()
        if not wf:
            return
        existing = (await db.execute(select(Task).where(Task.workflow_id == wf.id))).scalars().all()
        existing_by_title = {t.request_details: t for t in existing}
        for t_dict in (workflow_tasks or []):
            title = t_dict.get("title", "Untitled Task")
            role = t_dict.get("assignee_role", "backend")
            status = "COMPLETED" if title in completed_set else "PENDING"
            if title in existing_by_title:
                existing_by_title[title].status = status
                existing_by_title[title].requesting_agent_id = role
            else:
                new_t = Task(
                    workflow_id=wf.id,
                    requesting_agent_id=role,
                    status=status,
                    request_details=title,
                    payload=_json.dumps(t_dict, default=str),
                    response=t_dict.get("description", "")[:4000]
                )
                db.add(new_t)
        await db.commit()

def broadcast_tool_call(tool_name: str, details: str, event_type: str = "LOG_EMITTED", payload_extra: dict = None, agent_role: str = "", project_id: str = ""):
    """Broadcasts agent tool calls, file edits, web searches, and terminal commands live to the UI."""
    project_id = project_id or get_active_project_id()
    if not project_id:
        return

    effective_role = agent_role or get_active_agent_role() or "tool_execution"
    now_str = str(datetime.datetime.utcnow())
    msg = f"🛠️ **Tool Call**: `{tool_name}` → {details[:150]}"

    # Always log tool call in Chat panel with active agent attribution
    ws_manager.broadcast_sync(project_id, "LOG_EMITTED", {
        "agent_name": effective_role,
        "message": msg,
        "timestamp": now_str
    })
    _write_live_progress_md(
        active_stage=parent_stage_from_thread(""),
        active_agent=effective_role,
        sub_node=tool_name,
        new_event=msg,
    )
    
    # Save to DB for refresh recovery
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.create_task(_save_tool_log(project_id, tool_name, msg, effective_role))
            if event_type == "TERMINAL_COMMAND" and payload_extra:
                loop.create_task(_save_terminal_log(project_id, payload_extra, effective_role))
            elif event_type == "FILE_CHANGE" and payload_extra:
                loop.create_task(_save_file_record(project_id, payload_extra))
    except RuntimeError:
        if hasattr(ws_manager, 'main_loop') and ws_manager.main_loop:
            asyncio.run_coroutine_threadsafe(_save_tool_log(project_id, tool_name, msg, effective_role), ws_manager.main_loop)
            if event_type == "TERMINAL_COMMAND" and payload_extra:
                asyncio.run_coroutine_threadsafe(_save_terminal_log(project_id, payload_extra, effective_role), ws_manager.main_loop)
            elif event_type == "FILE_CHANGE" and payload_extra:
                asyncio.run_coroutine_threadsafe(_save_file_record(project_id, payload_extra), ws_manager.main_loop)

    # Extra panel specific broadcasts
    if event_type == "TERMINAL_COMMAND" and payload_extra:
        ws_manager.broadcast_sync(project_id, "TERMINAL_COMMAND", payload_extra)
    elif event_type == "FILE_CHANGE" and payload_extra:
        ws_manager.broadcast_sync(project_id, "FILE_CHANGE", payload_extra)

def broadcast_subgraph_node(sub_node: str, thread_id: str = ""):
    """Broadcasts internal subgraph node execution live to both the visual React Flow graph AND the Chat panel."""
    project_id = get_active_project_id()
    if not project_id and thread_id:
        project_id = thread_id.split("-")[0]
        
    if not project_id:
        return

    # 1. Update visual graph active node
    parent_stage = parent_stage_from_thread(thread_id)
    agent_role = effective_role_from_thread(thread_id) or get_active_agent_role()

    ws_manager.broadcast_sync(project_id, "SUBGRAPH_NODE_CHANGED", {
        "sub_node": sub_node,
        "thread_id": thread_id,
        "parent_stage": parent_stage,
        "agent_role": agent_role
    })

    # 2. Emit human-readable agent activity log to the Chat feed
    active_agent = get_active_agent_role() or "tool_execution"
    human_readable_subnode_names = {
        "write_code": "⚡ Writing source code files...",
        "write_ui_code": "🎨 Designing & implementing UI components...",
        "lint_code": "🔍 Running code linter & verifying syntax...",
        "run_tests": "🧪 Executing automated test suite...",
        "browser_check": "🌐 Validating app rendering & browser compatibility...",
        "push_to_github": "🚀 Pushing committed feature branch to GitHub...",
        "mark_task_complete": "✅ Sub-task completed successfully.",
        "pop_task": "📦 Moving to next sub-task in queue...",
        "clarification": "💬 Reviewing project requirement questions...",
        "generate_draft": "📝 Drafting feasibility & technical strategy...",
        "critique": "🧐 Conducting peer review & refining strategy...",
        "user_approval": "✋ Awaiting human review & approval...",
        "finalize": "📄 Finalizing output documents...",
        "approve_schema": "🗃️ Designing database schema...",
        "approve_api": "🔌 Drafting API contracts...",
        "approve_structure": "📁 Planning project directory topology...",
        "finalize_design": "🏗️ Finalizing system architecture design..."
    }

    friendly_text = human_readable_subnode_names.get(sub_node, f"Executing sub-node: `{sub_node}`")
    now_str = str(datetime.datetime.utcnow())

    ws_manager.broadcast_sync(project_id, "LOG_EMITTED", {
        "agent_name": effective_role_from_thread(thread_id) or active_agent,
        "message": friendly_text,
        "timestamp": now_str
    })
    _write_live_progress_md(
        active_stage=parent_stage,
        active_agent=effective_role_from_thread(thread_id) or active_agent,
        sub_node=sub_node,
        new_event=friendly_text,
    )
    
    # Fire and forget DB update
    import asyncio
    async def _update_db():
        from backend.database import AsyncSessionLocal
        from backend.models import Workflow, AgentLogModel
        from sqlalchemy import update, select
        p_id = _resolve_int_project_id(project_id)
        async with AsyncSessionLocal() as session:
            parent_stage = parent_stage_from_thread(thread_id)
            update_vals = {"current_subgraph_node": sub_node}
            wf = None
            if p_id is not None:
                stmt = select(Workflow).where(Workflow.project_id == p_id)
                wf = (await session.execute(stmt)).scalars().first()
            else:
                stmt = select(Workflow).order_by(Workflow.id.desc())
                wf = (await session.execute(stmt)).scalars().first()
            if parent_stage:
                update_vals["current_state"] = parent_stage
                if wf:
                    import json as _json
                    try:
                        completed_list = _json.loads(wf.completed_nodes) if wf.completed_nodes else []
                    except Exception:
                        completed_list = []
                    stage_order = [
                        "planning_stage", "pm_phase_a_stage", "architect_stage",
                        "task_breakdown_stage", "pm_phase_b_stage", "dispatcher_stage",
                        "database_engineer_stage", "backend_dev_stage", "frontend_dev_stage",
                        "qa_stage", "reviewer_stage", "security_stage", "devops_stage"
                    ]
                    if parent_stage in stage_order:
                        idx = stage_order.index(parent_stage)
                        for prev_stage in stage_order[:idx]:
                            if prev_stage not in completed_list:
                                completed_list.append(prev_stage)
                        update_vals["completed_nodes"] = _json.dumps(completed_list)

            if wf:
                await session.execute(
                    update(Workflow)
                    .where(Workflow.id == wf.id)
                    .values(**update_vals)
                )
                log_entry = AgentLogModel(
                    workflow_id=wf.id,
                    requesting_agent_id=effective_role_from_thread(thread_id) or active_agent,
                    status="SUBGRAPH_NODE",
                    request_details=friendly_text,
                    payload=sub_node,
                    response=parent_stage or ""
                )
                session.add(log_entry)
                await session.commit()

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.create_task(_update_db())
    except RuntimeError:
        if hasattr(ws_manager, 'main_loop') and ws_manager.main_loop:
            asyncio.run_coroutine_threadsafe(_update_db(), ws_manager.main_loop)
    except Exception:
        pass

def effective_role_from_thread(thread_id: str) -> str:
    if not thread_id:
        return ""
    lower = thread_id.lower()
    if "planning" in lower: return "planner"
    if "pm_a" in lower or "pm_b" in lower: return "product_manager"
    if "architect" in lower: return "architect"
    if "task_breakdown" in lower: return "task_breakdown"
    if "database" in lower: return "database_engineer"
    if "backend" in lower: return "backend_dev"
    if "frontend" in lower: return "frontend_dev"
    if "qa" in lower: return "qa"
    if "reviewer" in lower: return "reviewer"
    if "security" in lower: return "security"
    if "devops" in lower: return "devops"
    return ""

def parent_stage_from_thread(thread_id: str) -> str:
    if thread_id:
        lower = thread_id.lower()
        if "planning" in lower: return "planning_stage"
        if "pm_a" in lower: return "pm_phase_a_stage"
        if "architect" in lower: return "architect_stage"
        if "task_breakdown" in lower: return "task_breakdown_stage"
        if "pm_b" in lower: return "pm_phase_b_stage"
        if "database" in lower: return "database_engineer_stage"
        if "backend" in lower: return "backend_dev_stage"
        if "frontend" in lower: return "frontend_dev_stage"
        if "qa" in lower: return "qa_stage"
        if "reviewer" in lower: return "reviewer_stage"
        if "security" in lower: return "security_stage"
        if "devops" in lower: return "devops_stage"
    
    # Fallback to active agent role context
    role = get_active_agent_role()
    if role:
        r_lower = role.lower()
        if "planner" in r_lower or "planning" in r_lower: return "planning_stage"
        if "pm" in r_lower or "product" in r_lower: return "pm_phase_b_stage"
        if "architect" in r_lower: return "architect_stage"
        if "task_breakdown" in r_lower: return "task_breakdown_stage"
        if "database" in r_lower: return "database_engineer_stage"
        if "backend" in r_lower: return "backend_dev_stage"
        if "frontend" in r_lower: return "frontend_dev_stage"
        if "qa" in r_lower: return "qa_stage"
        if "reviewer" in r_lower: return "reviewer_stage"
        if "security" in r_lower: return "security_stage"
        if "devops" in r_lower: return "devops_stage"
        
    return ""


