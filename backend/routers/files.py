import asyncio
import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import FileRecord, Project
from backend.schemas import FileRecordResponse
from backend.git_service import GitService

router = APIRouter(prefix="/files", tags=["Files & Git Diff"])


async def _resolve_project_dir(project_id: Optional[int], db: AsyncSession) -> Optional[str]:
    if project_id is None:
        return None
    proj = await db.get(Project, project_id)
    if proj and getattr(proj, "path", None):
        return str(proj.path)
    return None


def _is_within_allowed_roots(candidate: Path, allowed_roots: List[Path]) -> bool:
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    for root in allowed_roots:
        try:
            if resolved.is_relative_to(root.resolve()):
                return True
        except (OSError, ValueError):
            continue
    return False


@router.get("/tree")
async def get_workspace_file_tree(
    dir_path: str = "output",
    project_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Get the file tree structure of the specified project's dedicated directory."""
    proj_dir = await _resolve_project_dir(project_id, db)
    if project_id is not None:
        if not proj_dir or not os.path.exists(proj_dir):
            return []
        return await asyncio.to_thread(GitService.list_file_tree, proj_dir)

    if dir_path == "output":
        from agents.src.shared.workspace import get_output_dir
        active_dir = str(get_output_dir(ensure_exists=False))
        target_dir = active_dir if os.path.exists(active_dir) else ("projects" if os.path.exists("projects") else ("output" if os.path.exists("output") else "."))
    else:
        target_dir = dir_path if os.path.exists(dir_path) else "."
    return await asyncio.to_thread(GitService.list_file_tree, target_dir)


@router.get("/content")
async def get_file_content(
    path: str,
    project_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve content of a specific file strictly scoped within the project's workspace."""
    from agents.src.shared.workspace import PROJECTS_DIR, ROOT_DIR, get_output_dir

    proj_dir = await _resolve_project_dir(project_id, db)
    allowed_roots: List[Path] = []
    if proj_dir:
        allowed_roots.append(Path(proj_dir))
    else:
        allowed_roots.extend([
            get_output_dir(ensure_exists=False),
            PROJECTS_DIR,
            ROOT_DIR / "output",
        ])

    candidates: List[Path] = []
    if proj_dir:
        candidates.append(Path(proj_dir) / path)
    candidates.append(Path(path))
    if not proj_dir:
        candidates.append(get_output_dir(ensure_exists=False) / path)
        candidates.append(ROOT_DIR / "output" / path)

    target_path: Optional[Path] = None
    for cand in candidates:
        if cand.exists() and cand.is_file():
            if not _is_within_allowed_roots(cand, allowed_roots):
                raise HTTPException(status_code=403, detail="Access denied: file is outside project workspace")
            target_path = cand.resolve()
            break

    if target_path is None:
        raise HTTPException(status_code=404, detail="File path not found")

    try:
        content = target_path.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@router.get("/git-diff")
async def get_overall_git_diff(
    project_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve current unified git diff scoped to the project's workspace directory."""
    proj_dir = await _resolve_project_dir(project_id, db)
    if project_id is not None and (not proj_dir or not os.path.exists(proj_dir)):
        return {"diff": ""}
    repo_path = proj_dir if (proj_dir and os.path.exists(os.path.join(proj_dir, ".git"))) else (proj_dir or ".")
    if proj_dir and not os.path.exists(os.path.join(proj_dir, ".git")):
        return {"diff": ""}
    diff = await asyncio.to_thread(GitService.get_git_diff, repo_path)
    return {"diff": diff}


@router.get("/git-diff/file")
async def get_file_git_diff(
    path: str,
    project_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve git diff for a specific file inside the project workspace."""
    proj_dir = await _resolve_project_dir(project_id, db)
    if proj_dir and not os.path.exists(os.path.join(proj_dir, ".git")):
        return {"file_path": path, "diff": ""}
    repo_path = proj_dir or "."
    diff = await asyncio.to_thread(GitService.get_file_diff, path, repo_path)
    return {"file_path": path, "diff": diff}


@router.get("/records/project/{project_id}", response_model=List[FileRecordResponse])
async def list_project_file_records(project_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieve recorded file changes for a project from database."""
    stmt = select(FileRecord).where(FileRecord.project_id == project_id).order_by(FileRecord.timestamp.desc())
    res = await db.execute(stmt)
    return res.scalars().all()
