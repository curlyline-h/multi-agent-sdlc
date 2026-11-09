from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import AgentLogModel, Workflow
from backend.schemas import AgentLogResponse

router = APIRouter(prefix="/logs", tags=["Agent Logs"])

@router.get("/project/{project_id}", response_model=List[AgentLogResponse])
async def list_project_logs(project_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve chronological agent logs for a project."""
    stmt = (
        select(AgentLogModel)
        .join(Workflow, AgentLogModel.workflow_id == Workflow.id)
        .where(Workflow.project_id == project_id)
        .order_by(AgentLogModel.created_at.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()
