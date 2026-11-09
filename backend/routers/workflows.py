from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import Workflow
from backend.schemas import WorkflowResponse

router = APIRouter(prefix="/workflows", tags=["Workflows"])

@router.get("/project/{project_id}", response_model=WorkflowResponse)
async def get_project_workflow(project_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve current workflow status for a project."""
    stmt = select(Workflow).where(Workflow.project_id == project_id)
    res = await db.execute(stmt)
    wf = res.scalars().first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found for project")
    return wf
