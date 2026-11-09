from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import Task, Workflow
from backend.schemas import TaskResponse

router = APIRouter(prefix="/tasks", tags=["Tasks"])

@router.get("/project/{project_id}", response_model=List[TaskResponse])
async def list_project_tasks(project_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve all tasks for a specific project."""
    stmt = select(Task).join(Workflow).where(Workflow.project_id == project_id).order_by(Task.created_at.asc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve a single task by ID."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
