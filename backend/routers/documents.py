from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.database import get_db
from backend.models import HumanApproval, Project, Workflow

router = APIRouter(prefix="/documents", tags=["Documents"])


def _classify_doc_type(title: str) -> str:
    lower_title = title.lower()
    if "prd" in lower_title:
        return "prd"
    if any(k in lower_title for k in ("design", "schema", "api", "structure")):
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
    """Extract project documents (Plan, PRD, Design docs, etc.) from approval records and workspace markdown artifacts."""
    stmt = (
        select(HumanApproval)
        .join(Workflow, HumanApproval.workflow_id == Workflow.id)
        .where(Workflow.project_id == project_id)
        .order_by(HumanApproval.created_at.asc())
    )
    result = await db.execute(stmt)
    approvals = result.scalars().all()

    docs = []
    seen_titles: set[str] = set()
    for a in approvals:
        doc_title = (a.request_details or "general").strip()
        if any(kw in doc_title.lower() for kw in ("plan", "prd", "schema", "api", "structure", "design", "security", "review")):
            docs.append({
                "id": f"approval-{a.id}",
                "title": doc_title,
                "type": _classify_doc_type(doc_title),
                "content": a.payload or "",
                "status": "approved" if a.status != "PENDING" else "draft",
                "agentRole": a.requesting_agent_id or "orchestrator",
                "updatedAt": str(a.updated_at or a.created_at or ""),
            })
            seen_titles.add(doc_title.lower())

    # Also include saved workspace markdown artifacts (e.g. final_prd.md, final_plan.md, final_design.md)
    proj = await db.get(Project, project_id)
    if proj and proj.path:
        proj_dir = Path(proj.path)
        if proj_dir.exists():
            for md_file in sorted(proj_dir.glob("*.md")):
                title = md_file.stem.replace("_", " ").title()
                if title.lower() in seen_titles or md_file.stem.lower() in seen_titles:
                    continue
                try:
                    content = md_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if not content.strip():
                    continue
                mtime = datetime.utcfromtimestamp(md_file.stat().st_mtime).isoformat()
                docs.append({
                    "id": f"file-{md_file.name}",
                    "title": md_file.name,
                    "type": _classify_doc_type(md_file.name),
                    "content": content,
                    "status": "approved" if md_file.name.startswith("final_") else "draft",
                    "agentRole": "orchestrator",
                    "updatedAt": mtime,
                })
                seen_titles.add(md_file.name.lower())

    return docs
