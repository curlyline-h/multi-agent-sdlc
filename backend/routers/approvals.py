from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import HumanApproval, Project, Workflow
from backend.schemas import HumanApprovalResponse, HumanApprovalSubmit
from backend.orchestrator_service import OrchestratorService

router = APIRouter(prefix="/approvals", tags=["Human Approvals"])

@router.get("/pending", response_model=List[HumanApprovalResponse])
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    """List all pending human approval requests requiring user intervention."""
    stmt = select(HumanApproval).where(HumanApproval.status == "PENDING").order_by(HumanApproval.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/project/{project_id}", response_model=List[HumanApprovalResponse])
async def list_project_approvals(project_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve all human approvals for a project."""
    stmt = (
        select(HumanApproval)
        .join(Workflow, HumanApproval.workflow_id == Workflow.id)
        .where(Workflow.project_id == project_id)
        .order_by(HumanApproval.created_at.desc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/{approval_id}/respond")
async def respond_to_approval(
    approval_id: int,
    payload: HumanApprovalSubmit,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Submit human feedback/approval decision to resume orchestrator pipeline execution."""
    approval = await db.get(HumanApproval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval.status != "PENDING":
        raise HTTPException(status_code=400, detail="Approval request has already been processed")

    wf = await db.get(Workflow, approval.workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow associated with approval not found")

    project = await db.get(Project, wf.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project associated with approval not found")

    feedback_text = payload.feedback or ""

    # Immediately mark approval as processed in DB
    approval.status = "APPROVED" if not feedback_text or feedback_text.lower() in ["approve", "yes", "ok"] else "FEEDBACK_SUBMITTED"
    approval.feed_back = feedback_text if feedback_text else "Approved"

    # If initial project description was short/greeting, update project.description in DB with user's detailed requirement
    if project and feedback_text:
        desc_lower = (project.description or "").strip().lower()
        if len(desc_lower) < 15 or desc_lower in ["hi", "hiiiii", "hello", "hey"]:
            project.description = feedback_text

    await db.commit()

    # Launch pipeline resume in background task
    background_tasks.add_task(
        OrchestratorService.run_pipeline_task,
        wf.project_id,
        str(wf.project_id),
        project.description or feedback_text,
        feedback_text
    )

    return {"status": "SUCCESS", "message": "Pipeline resumed with user feedback"}
