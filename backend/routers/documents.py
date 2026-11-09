from agents.src.rag import document_processor
from agents.src.rag import document_processor
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any

from backend.database import get_db
from backend.models import HumanApproval, Workflow

router = APIRouter(prefix="/documents", tags=["Documents"])

def _classify_doc_type(title: str) -> str:
    lower_title = title.lower()
    if "prd" in lower_title:
        return "prd"
    if "design" in lower_title or "schema" in lower_title or "api" in lower_title or "structure" in lower_title:
        return "design"
    if "task" in lower_title:
        return "task_breakdown"
    if "security" in lower_title:
        return "security_report"
    if "review" in lower_title:
        return "review"
    return "implementation_plan"

@router.get("/project/{project_id}")
async def get_project_documents(project_id: int, db: AsyncSession = Depends(get_db)):
    """Extract documents (PRD, design docs) from approval payloads."""
    stmt = (
        select(HumanApproval)
        .join(Workflow, HumanApproval.workflow_id == Workflow.id)
        .where(Workflow.project_id == project_id)
        .order_by(HumanApproval.created_at.asc())
    )
    result = await db.execute(stmt)
    approvals = result.scalars().all()
    
    docs = []
    for a in approvals:
        doc_type = a.request_details or "general"
        if any(kw in doc_type.lower() for kw in ["prd", "schema", "api", "structure", "design"]):
            docs.append({
                "id": str(a.id),
                "title": doc_type,
                "type": _classify_doc_type(doc_type),
                "content": a.payload or "",
                "status": "approved" if a.status != "PENDING" else "draft",
                "agentRole": a.requesting_agent_id,
                "updatedAt": str(a.updated_at)
            })
        LLM_MODEL='gemma4:31b-cloud'
        LLM_PROVIDER='ollama'
    return docs
