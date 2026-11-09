from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import CommandExecution
from backend.schemas import CommandExecutionResponse

router = APIRouter(prefix="/terminal", tags=["Terminal Command Logs"])

@router.get("/project/{project_id}", response_model=List[CommandExecutionResponse])
async def list_project_terminal_commands(project_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve chronological command execution logs for terminal display."""
    stmt = select(CommandExecution).where(CommandExecution.project_id == project_id).order_by(CommandExecution.timestamp.asc())
    res = await db.execute(stmt)
    return res.scalars().all()
