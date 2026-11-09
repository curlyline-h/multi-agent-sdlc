import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import Project, Workflow, HumanApproval
from backend.schemas import ProjectCreate, ProjectResponse
from backend.orchestrator_service import OrchestratorService

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("", response_model=ProjectResponse)
async def create_project(
    payload: ProjectCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Create a new SDLC project and start the multi-agent orchestrator in the background."""
    new_project = Project(
        title=payload.name,
        description=payload.user_req,
        path="",
        git_url="",
        current_status="RUNNING"
    )
    db.add(new_project)
    await db.commit()
    await db.refresh(new_project)

    thread_id = str(new_project.id)
    new_workflow = Workflow(
        project_id=new_project.id,
        current_state="START",
        status="RUNNING",
        source_branch="main",
        target_branch="main",
        next_agent="",
        summary=""
    )
    db.add(new_workflow)
    await db.commit()

    # Launch orchestrator in background task
    background_tasks.add_task(
        OrchestratorService.run_pipeline_task,
        new_project.id,
        thread_id,
        payload.user_req
    )

    return new_project

@router.get("", response_model=List[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """Retrieve all SDLC projects."""
    stmt = select(Project).order_by(Project.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/latest", response_model=ProjectResponse)
async def get_latest_project(db: AsyncSession = Depends(get_db)):
    """Retrieve the most recent SDLC project."""
    stmt = select(Project).order_by(Project.id.desc()).limit(1)
    res = await db.execute(stmt)
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="No projects found")
    return project

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve a single project by ID."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.post("/{project_id}/resume", response_model=ProjectResponse)
async def resume_project_pipeline(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Resume the multi-agent pipeline for an existing project.
    
    Returns 409 Conflict if the pipeline has a pending human approval —
    in that case the frontend must submit via POST /approvals/{id}/respond instead.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Guard: if a PENDING approval exists, reject the blind resume so we don't
    # corrupt LangGraph's interrupt checkpoint with a null-feedback Command.
    stmt = (
        select(HumanApproval)
        .join(Workflow, HumanApproval.workflow_id == Workflow.id)
        .where(
            Workflow.project_id == project_id,
            HumanApproval.status == "PENDING"
        )
    )
    res = await db.execute(stmt)
    pending_approval = res.scalars().first()
    if pending_approval:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline has a pending approval (id={pending_approval.id}). Submit via POST /approvals/{pending_approval.id}/respond."
        )

    thread_id = str(project.id)
    background_tasks.add_task(
        OrchestratorService.run_pipeline_task,
        project.id,
        thread_id,
        project.description or "Resume pipeline"
    )
    return project

