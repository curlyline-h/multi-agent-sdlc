import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models import Project, Task, Workflow, AgentLogModel, HumanApproval, CommandExecution, FileRecord
from backend.websocket_manager import ws_manager
from backend.git_service import GitService

# Eagerly import heavy dependencies to prevent blocking the event loop on first request
from agents.src.orchestrator.graph import parent_workflow
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

logger = logging.getLogger("orchestrator_service")

_active_pipelines = set()

class OrchestratorService:
    @staticmethod
    async def run_pipeline_task(project_id: int, thread_id: str, user_req: str, resume_feedback: Optional[str] = None):
        """Asynchronously runs or resumes the LangGraph orchestration graph stream and syncs with DB & WebSockets."""
        
        # Prevent concurrent duplicate executions of the exact same thread
        if thread_id in _active_pipelines:
            logger.warning(f"Pipeline {thread_id} is already actively running. Ignoring duplicate start request.")
            return
            
        _active_pipelines.add(thread_id)
        
        try:
            from backend.telemetry import set_active_project_id
            set_active_project_id(str(project_id))
    
            async with AsyncSessionLocal() as db:
                try:
                    # Use eagerly loaded graph & checkpointer

                    async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
                        await checkpointer.setup()
                        orchestration_graph = parent_workflow.compile(checkpointer=checkpointer)

                        config = {"configurable": {"thread_id": thread_id}}

                        graph_state = await orchestration_graph.aget_state(config)

                        if resume_feedback is not None:
                            current_input = Command(resume=resume_feedback)
                            logger.info(f"Resuming pipeline thread {thread_id} with feedback")
                            # Update pending approval status in DB
                            stmt = select(HumanApproval).join(Workflow).where(
                                Workflow.project_id == project_id,
                                HumanApproval.status == "PENDING"
                            )
                            res = await db.execute(stmt)
                            pending_app = res.scalars().first()
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

                        # Update workflow status to RUNNING in DB
                        stmt = select(Workflow).where(Workflow.project_id == project_id)
                        res = await db.execute(stmt)
                        wf = res.scalars().first()
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

                            import json as _json
                            if isinstance(interrupt_payload, dict) and "questions" in interrupt_payload:
                                pay_load = _json.dumps(interrupt_payload["questions"])
                            else:
                                pay_load = (interrupt_payload.get("draft") or interrupt_payload.get("content") or interrupt_payload.get("message")) if isinstance(interrupt_payload, dict) else str(interrupt_payload)
                                pay_load = pay_load or "Approval Details"

                            # Save human approval entry
                            app_entry = HumanApproval(
                                workflow_id=wf.id,
                                requesting_agent_id="orchestrator",
                                status="PENDING",
                                request_details=req_details,
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

                        elif not graph_state.next and not has_interrupts:
                            wf.status = "COMPLETED"
                            wf.current_state = "COMPLETED"
                            proj = await db.get(Project, project_id)
                            if proj:
                                proj.current_status = "COMPLETED"
                            await db.commit()

                            await ws_manager.broadcast(str(project_id), "STAGE_CHANGED", {
                                "stage": "COMPLETED",
                                "state": "COMPLETED"
                            })

                except Exception as e:
                    logger.error(f"Error executing orchestrator pipeline for project {project_id}: {e}", exc_info=True)
                    stmt = select(Workflow).where(Workflow.project_id == project_id)
                    res = await db.execute(stmt)
                    wf = res.scalars().first()
                    if wf:
                        wf.status = "FAILED"
                        await db.commit()
                    await ws_manager.broadcast(str(project_id), "ERROR", {"message": str(e)})
        finally:
            _active_pipelines.remove(thread_id)

    @staticmethod
    async def _process_node_event(db: AsyncSession, project_id: int, thread_id: str, node_name: str, state_update: Any, wf: Workflow):
        """Processes a single node event from LangGraph, updating DB and sending WS broadcasts."""
        import json as _json

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
            await ws_manager.broadcast(str(project_id), "STAGE_CHANGED", {
                "stage": node_name,
                "active_role": wf.next_agent or node_name,
                "state": wf.status
            })

        if not isinstance(state_update, dict):
            return

        # 1. Active / Workflow tasks updates
        if "workflow_tasks" in state_update:
            for task_data in state_update["workflow_tasks"]:
                if isinstance(task_data, dict):
                    title = task_data.get("title", "Untitled")
                    new_t = Task(
                        workflow_id=wf.id,
                        requesting_agent_id=task_data.get("assignee_role", "dispatcher"),
                        status=task_data.get("status", "PENDING"),
                        request_details=title,
                        payload=task_data.get("description", "") or "",
                        response=""
                    )
                    db.add(new_t)
            await db.commit()

            await ws_manager.broadcast(str(project_id), "TASKS_UPDATED", {
                "tasks": state_update["workflow_tasks"]
            })

        # 2. File changes
        if "final_file_changes" in state_update and state_update["final_file_changes"]:
            for fc in state_update["final_file_changes"]:
                path = fc.get("path", str(fc)) if isinstance(fc, dict) else str(fc)
                action = fc.get("action", "MODIFIED") if isinstance(fc, dict) else "MODIFIED"
                diff_text = GitService.get_file_diff(path)

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
            "timestamp": str(datetime.utcnow())
        })

        # 4. Git overall diff broadcast
        current_diff = GitService.get_git_diff()
        if current_diff:
            await ws_manager.broadcast(str(project_id), "GIT_DIFF", {
                "diff": current_diff
            })
