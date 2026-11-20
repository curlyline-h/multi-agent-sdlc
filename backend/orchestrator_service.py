import asyncio
import json as _json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.database import AsyncSessionLocal
from backend.models import Project, Task, Workflow, AgentLogModel, HumanApproval, FileRecord
from backend.websocket_manager import ws_manager
from backend.git_service import GitService

# Eagerly import heavy dependencies to prevent blocking the event loop on first request
from agents.src.orchestrator.graph import parent_workflow
from langgraph.types import Command

logger = logging.getLogger("orchestrator_service")

_active_pipelines: set[str] = set()
_active_tasks: dict[str, asyncio.Task] = {}
_stop_requested: set[str] = set()

class OrchestratorService:
    @staticmethod
    async def stop_pipeline_task(project_id: int, db: AsyncSession) -> bool:
        """Stops a running pipeline for project_id, cancels its asyncio task, and marks it STOPPED."""
        pid_key = str(project_id)
        _stop_requested.add(pid_key)

        task = _active_tasks.get(pid_key)
        cancelled = False
        if task and not task.done():
            task.cancel()
            cancelled = True

        stmt = select(Workflow).where(Workflow.project_id == project_id)
        wf: Any = (await db.execute(stmt)).scalars().first()
        proj: Any = await db.get(Project, project_id)
        if proj and proj.current_status == "COMPLETED":
            return False
        if wf and wf.status in ("RUNNING", "AWAITING_APPROVAL", "PAUSED"):
            wf.status = "STOPPED"
        if proj and proj.current_status not in ("COMPLETED",):
            proj.current_status = "STOPPED"
        await db.commit()

        await ws_manager.broadcast(pid_key, "STAGE_CHANGED", {
            "stage": "STOPPED",
            "active_role": "orchestrator",
            "state": "STOPPED",
        })
        await ws_manager.broadcast(pid_key, "LOG_EMITTED", {
            "agent_name": "orchestrator",
            "message": "🛑 Session stopped by user.",
            "timestamp": str(datetime.now(timezone.utc).replace(tzinfo=None)),
        })
        return cancelled

    @staticmethod
    async def recover_stale_workflows():
        """Marks any workflows left in RUNNING after an unclean shutdown as PAUSED."""
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Workflow)
                .where(Workflow.status == "RUNNING")
                .values(status="PAUSED")
            )
            await db.commit()

    @staticmethod
    async def run_pipeline_task(project_id: int, thread_id: str, user_req: str, resume_feedback: Optional[str] = None):
        """Asynchronously runs or resumes the LangGraph orchestration graph stream and syncs with DB & WebSockets."""
        
        # Prevent concurrent duplicate executions of the exact same thread
        if thread_id in _active_pipelines:
            logger.warning(f"Pipeline {thread_id} is already actively running. Ignoring duplicate start request.")
            return
            
        _active_pipelines.add(thread_id)
        pid_key = str(project_id)
        _stop_requested.discard(pid_key)
        cur_task = asyncio.current_task()
        if cur_task is not None:
            _active_tasks[pid_key] = cur_task
        
        try:
            from backend.telemetry import set_active_project_id
            set_active_project_id(str(project_id))
    
            async with AsyncSessionLocal() as db:
                try:
                    # Use eagerly loaded graph & checkpointer

                    from agents.src.shared.checkpointer import get_async_checkpointer
                    async with get_async_checkpointer("checkpoints.sqlite") as checkpointer:
                        orchestration_graph = parent_workflow.compile(checkpointer=checkpointer)

                        config: Any = {"configurable": {"thread_id": thread_id}}

                        graph_state = await orchestration_graph.aget_state(config)

                        # Resolve & activate isolated per-project directory under projects/<slug>/
                        proj_stmt = select(Project).where(Project.id == project_id)
                        proj_res = await db.execute(proj_stmt)
                        proj_row: Any = proj_res.scalars().first()
                        raw_name = (getattr(proj_row, "title", None) or "").strip() if proj_row else ""
                        proj_label = user_req if (not raw_name or raw_name.lower().startswith("sdlc project")) else raw_name

                        from agents.src.shared.workspace import set_active_project_dir
                        from pathlib import Path as _Path
                        import re as _re
                        is_resuming = (resume_feedback is not None) or bool(graph_state.next)
                        existing_path = (getattr(proj_row, "path", None) or "").strip() if proj_row else ""
                        # If the workspace was originally created from a greeting (e.g. projects/hi-4)
                        # and is still completely empty while the user has now provided a real project description,
                        # migrate the workspace folder to a clean slug matching the real project.
                        _greeting_slug_re = _re.compile(r"^(hi|hii+|hello|hey|hi-there|hello-there|hey-there|project)(-\d+)?$")
                        _existing_dir = _Path(existing_path) if existing_path else None
                        _is_empty_greeting_dir = (
                            _existing_dir is not None
                            and _existing_dir.exists()
                            and _greeting_slug_re.match(_existing_dir.name.lower()) is not None
                            and not any(_existing_dir.iterdir())
                        )
                        if (
                            is_resuming
                            and proj_row
                            and _is_empty_greeting_dir
                            and len((proj_row.description or "").strip()) >= 15
                        ):
                            try:
                                _existing_dir.rmdir()
                            except OSError:
                                pass
                            active_project_dir = set_active_project_dir(
                                proj_row.description,
                                unique_if_exists=True,
                            )
                            proj_row.path = str(active_project_dir)
                            await db.commit()
                        elif existing_path:
                            active_project_dir = set_active_project_dir(project_dir=existing_path)
                        else:
                            active_project_dir = set_active_project_dir(
                                proj_label,
                                unique_if_exists=not is_resuming,
                            )
                            if proj_row:
                                proj_row.path = str(active_project_dir)
                                await db.commit()
                        logger.info(f"Active project workspace: {active_project_dir}")

                        current_input: Any
                        if resume_feedback is not None:
                            current_input = Command(resume=resume_feedback)
                            logger.info(f"Resuming pipeline thread {thread_id} with feedback")
                            # Update pending approval status in DB
                            stmt = select(HumanApproval).join(Workflow).where(
                                Workflow.project_id == project_id,
                                HumanApproval.status == "PENDING"
                            )
                            res = await db.execute(stmt)
                            pending_app: Any = res.scalars().first()
                            if pending_app:
                                pending_app.status = "APPROVED" if not resume_feedback else "FEEDBACK_SUBMITTED"
                                pending_app.feed_back = resume_feedback
                                await db.commit()
                        elif graph_state.next:
                            # Resume a previously started, non-interrupted workflow (e.g. recovering from a crash)
                            current_input = None
                            logger.info(f"Resuming crashed/paused pipeline thread {thread_id} from state: {graph_state.next}")
                        else:
                            # Brand new workflow
                            current_input = {
                                "user_req": user_req,
                                "workflowId": thread_id,
                                "projectId": str(project_id),
                                "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
                                "prd": "",
                                "project_name": active_project_dir.name,
                                "final_design_doc": "",
                                "final_file_changes": [],
                                "agent_logs": [],
                                "human_interventions": [],
                                "completed_task_titles": [],
                                "workflow_tasks": [],
                                "active_tasks": [],
                                "github_repo_name": "",
                            }

                        # Update workflow status to RUNNING in DB
                        stmt = select(Workflow).where(Workflow.project_id == project_id)
                        res = await db.execute(stmt)
                        wf: Any = res.scalars().first()
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
                            await db.commit()

                        # Stream orchestration graph
                        async for event in orchestration_graph.astream(current_input, config=config):
                            if pid_key in _stop_requested:
                                logger.info(f"Stop requested for project {project_id}; halting stream.")
                                raise asyncio.CancelledError()
                            for node_name, state_update in event.items():
                                await OrchestratorService._process_node_event(db, project_id, thread_id, node_name, state_update, wf)

                        # Post-stream: check if interrupted or completed
                        graph_state = await orchestration_graph.aget_state(config)
                        has_interrupts = False
                        interrupt_payload = None

                        if graph_state.tasks:
                            for t in graph_state.tasks:
                                if hasattr(t, "interrupts") and t.interrupts:
                                    has_interrupts = True
                                    interrupt_payload = t.interrupts[0].value
                                    break

                        if has_interrupts and interrupt_payload:
                            wf.status = "AWAITING_APPROVAL"
                            if graph_state.next and graph_state.next[0]:
                                wf.current_state = graph_state.next[0]
                            await db.commit()

                            req_details = (interrupt_payload.get("section") or interrupt_payload.get("type") or interrupt_payload.get("message")) if isinstance(interrupt_payload, dict) else "Approval Required"
                            req_details = req_details or "Approval Required"

                            if isinstance(interrupt_payload, dict) and "questions" in interrupt_payload:
                                pay_load = _json.dumps(interrupt_payload["questions"])
                            else:
                                raw_payload = (interrupt_payload.get("draft") or interrupt_payload.get("content") or interrupt_payload.get("message")) if isinstance(interrupt_payload, dict) else str(interrupt_payload)
                                if not raw_payload:
                                    pay_load = "Approval Details"
                                elif isinstance(raw_payload, str):
                                    pay_load = raw_payload
                                else:
                                    pay_load = _json.dumps(raw_payload, default=str)

                            # Save human approval entry
                            app_entry = HumanApproval(
                                workflow_id=wf.id,
                                requesting_agent_id="orchestrator",
                                status="PENDING",
                                request_details=str(req_details),
                                payload=pay_load,
                                feed_back=""
                            )
                            db.add(app_entry)
                            await db.commit()

                            # Broadcast interrupt over WebSockets
                            await ws_manager.broadcast(str(project_id), "HUMAN_INTERRUPT", {
                                "approval_id": app_entry.id,
                                "type": interrupt_payload.get("type", "draft_review") if isinstance(interrupt_payload, dict) else "draft_review",
                                "section": app_entry.request_details,
                                "questions": interrupt_payload.get("questions", []) if isinstance(interrupt_payload, dict) else [],
                                "content": app_entry.payload
                            })

                            # Emit a concise status log in chat (full interactive card is already rendered by HUMAN_INTERRUPT)
                            questions_list = interrupt_payload.get("questions", []) if isinstance(interrupt_payload, dict) else []
                            if not questions_list:
                                import re as _re
                                from agents.src.shared.workspace import get_artifact_path
                                safe_sec = _re.sub(r"[^a-z0-9_-]", "_", str(app_entry.request_details).lower()).strip("_") or "review"
                                draft_filename = f"{safe_sec}_draft.md"
                                try:
                                    draft_path = get_artifact_path(draft_filename)
                                    draft_path.write_text(pay_load, encoding="utf-8")
                                    await ws_manager.broadcast(str(project_id), "FILE_CHANGE", {
                                        "path": draft_filename,
                                        "action": "CREATED",
                                        "diff": "",
                                    })
                                except Exception as draft_err:
                                    logger.warning(f"Could not save draft markdown {draft_filename}: {draft_err}")
                                await ws_manager.broadcast(str(project_id), "LOG_EMITTED", {
                                    "agent_name": "orchestrator",
                                    "message": f"✋ **Approval Required ({app_entry.request_details})** — saved `{draft_filename}` to your project folder.",
                                    "timestamp": str(datetime.now(timezone.utc).replace(tzinfo=None))
                                })

                        elif not graph_state.next and not has_interrupts:
                            wf.status = "COMPLETED"
                            wf.current_state = "COMPLETED"
                            proj: Any = await db.get(Project, project_id)
                            if proj:
                                proj.current_status = "COMPLETED"
                            await db.commit()

                            await ws_manager.broadcast(str(project_id), "STAGE_CHANGED", {
                                "stage": "COMPLETED",
                                "state": "COMPLETED"
                            })

                except asyncio.CancelledError:
                    logger.info(f"Pipeline cancelled/stopped for project {project_id}")
                    await db.rollback()
                    stmt = select(Workflow).where(Workflow.project_id == project_id)
                    wf_stop: Any = (await db.execute(stmt)).scalars().first()
                    if wf_stop:
                        wf_stop.status = "STOPPED"
                    proj_stop: Any = await db.get(Project, project_id)
                    if proj_stop and proj_stop.current_status != "COMPLETED":
                        proj_stop.current_status = "STOPPED"
                    await db.commit()
                except Exception as e:
                    logger.error(f"Error executing orchestrator pipeline for project {project_id}: {e}", exc_info=True)
                    await db.rollback()
                    stmt = select(Workflow).where(Workflow.project_id == project_id)
                    res = await db.execute(stmt)
                    wf_err: Any = res.scalars().first()
                    if wf_err:
                        wf_err.status = "FAILED"
                        await db.commit()
                    await ws_manager.broadcast(str(project_id), "ERROR", {"message": str(e)})
        finally:
            _active_pipelines.discard(thread_id)
            _active_tasks.pop(str(project_id), None)
            _stop_requested.discard(str(project_id))

    @staticmethod
    async def _process_node_event(db: AsyncSession, project_id: int, thread_id: str, node_name: str, state_update: Any, wf: Any):
        """Processes a single node event from LangGraph, updating DB and sending WS broadcasts."""
        # Track completed nodes for graph state restoration on refresh
        completed = _json.loads(wf.completed_nodes or "[]")

        # LangGraph virtual nodes — they carry no real state and must be ignored
        VIRTUAL_NODES = {"__interrupt__", "__start__"}
        is_virtual = node_name in VIRTUAL_NODES
        is_new_node = not is_virtual and wf.current_state != node_name

        if is_new_node and wf.current_state and wf.current_state not in completed:
            completed.append(wf.current_state)
            wf.completed_nodes = _json.dumps(completed)

        if not is_virtual:
            wf.current_state = node_name
        if isinstance(state_update, dict) and "active_role" in state_update:
            wf.next_agent = state_update["active_role"]

        await db.commit()

        # Broadcast stage transition when a non-virtual parent node executes
        if not is_virtual:
            stage_summary = str(state_update.get("summary", "")) if isinstance(state_update, dict) else ""
            await ws_manager.broadcast(str(project_id), "STAGE_CHANGED", {
                "stage": node_name,
                "active_role": wf.next_agent or node_name,
                "state": wf.status,
                "rejected": "REJECTED" in stage_summary,
            })

        if not isinstance(state_update, dict):
            return

        # 1. Active / Workflow tasks updates (deduplicate + sync COMPLETED status)
        if "workflow_tasks" in state_update or "completed_task_titles" in state_update:
            existing_rows = (
                await db.execute(select(Task).where(Task.workflow_id == wf.id))
            ).scalars().all()
            by_title: dict[str, Any] = {str(r.request_details): r for r in existing_rows}
            completed_set = set(state_update.get("completed_task_titles") or [])

            for task_data in (state_update.get("workflow_tasks") or []):
                if not isinstance(task_data, dict):
                    continue
                title = task_data.get("title", "Untitled")
                desired_status = "COMPLETED" if title in completed_set else task_data.get("status", "PENDING")
                if title in by_title:
                    if by_title[title].status != desired_status:
                        by_title[title].status = desired_status
                else:
                    new_t = Task(
                        workflow_id=wf.id,
                        requesting_agent_id=task_data.get("assignee_role", "dispatcher"),
                        status=desired_status,
                        request_details=title,
                        payload=task_data.get("description", "") or "",
                        response=""
                    )
                    db.add(new_t)
                    by_title[title] = new_t

            for title in completed_set:
                if title in by_title and by_title[title].status != "COMPLETED":
                    by_title[title].status = "COMPLETED"

            await db.commit()

            all_tasks_payload = [
                {
                    "title": r.request_details,
                    "assignee_role": r.requesting_agent_id,
                    "status": r.status,
                }
                for r in by_title.values()
            ]
            await ws_manager.broadcast(str(project_id), "TASKS_UPDATED", {
                "tasks": all_tasks_payload,
                "completed_task_titles": list(completed_set),
                "completed_count": sum(1 for r in by_title.values() if r.status == "COMPLETED"),
                "total_count": len(by_title),
            })

        # Resolve project workspace dir for scoped git diffs
        proj_for_diff: Any = await db.get(Project, project_id)
        proj_dir = (getattr(proj_for_diff, "path", None) or "").strip() if proj_for_diff else ""
        has_proj_git = bool(proj_dir and os.path.exists(os.path.join(proj_dir, ".git")))

        # 2. File changes
        if "final_file_changes" in state_update and state_update["final_file_changes"]:
            for fc in state_update["final_file_changes"]:
                path = fc.get("path", str(fc)) if isinstance(fc, dict) else str(fc)
                action = fc.get("action", "MODIFIED") if isinstance(fc, dict) else "MODIFIED"
                diff_text = await asyncio.to_thread(GitService.get_file_diff, path, proj_dir) if has_proj_git else ""

                rec = FileRecord(
                    project_id=project_id,
                    file_path=path,
                    action=action,
                    diff_snapshot=diff_text or "",
                    content_snapshot=""
                )
                db.add(rec)

                await ws_manager.broadcast(str(project_id), "FILE_CHANGE", {
                    "path": path,
                    "action": action,
                    "diff": diff_text
                })
            await db.commit()

        # 3. Log entries with rich human-readable status
        node_descriptions = {
            "planning_stage": "✅ Planning Agent completed project requirements and initial strategy.",
            "pm_phase_a_stage": "✅ Product Manager finalized the Product Requirements Document (PRD).",
            "pm_phase_b_stage": "✅ Product Manager validated feature scope and technical prerequisites.",
            "architect_stage": "✅ Architect Agent finalized system topology, data schemas, and API contracts.",
            "task_breakdown_stage": "✅ Task Breakdown Agent successfully partitioned requirements into actionable sub-tasks.",
            "dispatcher_stage": "✅ Dispatcher Agent routed work to active developers.",
            "database_engineer_stage": "✅ Database Engineer generated SQL migrations and database schemas.",
            "backend_dev_stage": "✅ Backend Developer completed server endpoints and services.",
            "frontend_dev_stage": "✅ Frontend Developer finished responsive UI components and rendering.",
            "qa_stage": "✅ QA Agent executed automated test suites and validated edge cases.",
            "reviewer_stage": "✅ Code Reviewer inspected pull requests and conducted code audits.",
            "security_stage": "✅ Security Agent performed vulnerability scans and dependency checks.",
            "devops_stage": "✅ DevOps Agent built Docker containers and configured deployment pipelines."
        }

        log_msg = node_descriptions.get(node_name, f"Agent completed stage: {node_name}")
        if isinstance(state_update, dict):
            if "summary" in state_update and state_update["summary"]:
                log_msg = state_update["summary"]
            elif "message" in state_update and state_update["message"]:
                log_msg = state_update["message"]

        log_entry = AgentLogModel(
            workflow_id=wf.id,
            requesting_agent_id=node_name,
            status="INFO",
            request_details=log_msg,
            payload="",
            response=""
        )
        db.add(log_entry)
        await db.commit()

        await ws_manager.broadcast(str(project_id), "LOG_EMITTED", {
            "agent_name": node_name,
            "message": log_msg,
            "timestamp": str(datetime.now(timezone.utc).replace(tzinfo=None))
        })

        # 4. Git overall diff broadcast (non-blocking, strictly scoped to the project's git repo)
        if has_proj_git:
            current_diff = await asyncio.to_thread(GitService.get_git_diff, proj_dir)
            if current_diff:
                await ws_manager.broadcast(str(project_id), "GIT_DIFF", {
                    "diff": current_diff
                })
