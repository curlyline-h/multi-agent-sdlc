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

async def _save_tool_log(project_id: str, tool_name: str, msg: str, agent_role: str = ""):
    from backend.database import async_session_maker
    from backend.models import AgentLogModel, Workflow
    from sqlalchemy import select
    async with async_session_maker() as db:
        stmt = select(Workflow).where(Workflow.project_id == int(project_id))
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

async def _save_terminal_log(project_id: str, payload_extra: dict):
    from backend.database import async_session_maker
    from backend.models import CommandExecution, Workflow
    from sqlalchemy import select
    async with async_session_maker() as db:
        stmt = select(Workflow).where(Workflow.project_id == int(project_id))
        wf = (await db.execute(stmt)).scalars().first()
        if wf:
            cmd = payload_extra.get("command", "")
            stdout = payload_extra.get("stdout", "")
            stderr = payload_extra.get("stderr", "")
            exit_code = payload_extra.get("exit_code", 0)
            log_entry = CommandExecution(
                project_id=int(project_id),
                command=cmd,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code
            )
            db.add(log_entry)
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
    
    # Save to DB for refresh recovery
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.create_task(_save_tool_log(project_id, tool_name, msg, effective_role))
            if event_type == "TERMINAL_COMMAND" and payload_extra:
                loop.create_task(_save_terminal_log(project_id, payload_extra))
    except RuntimeError:
        if hasattr(ws_manager, 'main_loop') and ws_manager.main_loop:
            asyncio.run_coroutine_threadsafe(_save_tool_log(project_id, tool_name, msg, effective_role), ws_manager.main_loop)
            if event_type == "TERMINAL_COMMAND" and payload_extra:
                asyncio.run_coroutine_threadsafe(_save_terminal_log(project_id, payload_extra), ws_manager.main_loop)

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
    
    # Fire and forget DB update
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            async def _update_db():
                from backend.database import AsyncSessionLocal
                from backend.models import Workflow
                from sqlalchemy import update, select
                async with AsyncSessionLocal() as session:
                    parent_stage = parent_stage_from_thread(thread_id)
                    update_vals = {"current_subgraph_node": sub_node}
                    if parent_stage:
                        update_vals["current_state"] = parent_stage

                        try:
                            p_id = int(project_id)
                        except (ValueError, TypeError):
                            p_id = None
                        if p_id is not None:
                            stmt = select(Workflow).where(Workflow.project_id == p_id)
                            wf = (await session.execute(stmt)).scalars().first()
                        if wf:
                            import json as _json
                            try:
                                completed_list = _json.loads(wf.completed_nodes) if wf.completed_nodes else []
                            except Exception:
                                completed_list = []
                            
                            # Add previous nodes before parent_stage
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

                    await session.execute(
                        update(Workflow)
                        .where(Workflow.project_id == int(project_id))
                        .values(**update_vals)
                    )
                    await session.commit()
            loop.create_task(_update_db())
    except RuntimeError:
        if hasattr(ws_manager, 'main_loop') and ws_manager.main_loop:
            async def _update_db_threadsafe():
                from backend.database import AsyncSessionLocal
                from backend.models import Workflow
                from sqlalchemy import update, select
                async with AsyncSessionLocal() as session:
                    parent_stage = parent_stage_from_thread(thread_id)
                    update_vals = {"current_subgraph_node": sub_node}
                    if parent_stage:
                        update_vals["current_state"] = parent_stage
                        stmt = select(Workflow).where(Workflow.project_id == int(project_id))
                        wf = (await session.execute(stmt)).scalars().first()
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
                    await session.execute(
                        update(Workflow)
                        .where(Workflow.project_id == int(project_id))
                        .values(**update_vals)
                    )
                    await session.commit()
            asyncio.run_coroutine_threadsafe(_update_db_threadsafe(), ws_manager.main_loop)
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


