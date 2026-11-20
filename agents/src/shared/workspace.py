"""
Centralized per-project workspace isolation for the SDLC orchestrator.

Every generated project gets its own dedicated folder under ``projects/<slug>/``
so that its PRDs, design docs, task breakdowns, and generated source files never
mix with the parent ``sdlc`` repository or with other generated projects.
"""
from __future__ import annotations

import contextvars
import os
import re
import threading
from pathlib import Path
from typing import List, Optional, Union

ROOT_DIR: Path = Path(__file__).resolve().parents[3]
PROJECTS_DIR: Path = ROOT_DIR / "projects"
ENV_PROJECT_DIR_KEY = "SDLC_PROJECT_OUTPUT_DIR"

_LOCK = threading.Lock()
_ACTIVE_OUTPUT_DIR: Optional[Path] = None
_CTX_OUTPUT_DIR: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar("SDLC_CTX_OUTPUT_DIR", default=None)

_STOP_WORDS = {
    "i", "want", "you", "to", "a", "an", "the", "create", "build", "make",
    "develop", "design", "generate", "write", "for", "me", "please", "with",
    "using", "and", "or", "of", "in", "on", "where", "users", "user", "can",
    "their", "own", "that", "which", "who",
}


def slugify_project_name(name_or_req: str) -> str:
    """Builds a clean, Windows/POSIX-safe folder slug from a project name or prompt."""
    raw = (name_or_req or "").strip().lower()
    if not raw:
        return "project"

    raw = re.sub(r"\bto-do\b", "todo", raw)
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", raw)
    tokens = [t for t in re.split(r"[\s-]+", cleaned) if t]
    meaningful = [t for t in tokens if t not in _STOP_WORDS]
    chosen = meaningful[:4] if meaningful else tokens[:4]
    slug = "-".join(chosen).strip("-")[:60].strip("-")
    return slug or "project"


def set_active_project_dir(
    name_or_req: str = "",
    *,
    project_dir: Optional[Union[str, Path]] = None,
    create: bool = True,
    unique_if_exists: bool = False,
) -> Path:
    """
    Sets the active project workspace directory for the current process (and
    child subprocesses via ``SDLC_PROJECT_OUTPUT_DIR``).
    """
    global _ACTIVE_OUTPUT_DIR

    with _LOCK:
        if project_dir is not None:
            target = Path(project_dir)
            if not target.is_absolute():
                target = ROOT_DIR / target
        else:
            PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
            slug = slugify_project_name(name_or_req)
            target = PROJECTS_DIR / slug
            if unique_if_exists and target.exists():
                idx = 2
                while (PROJECTS_DIR / f"{slug}-{idx}").exists():
                    idx += 1
                target = PROJECTS_DIR / f"{slug}-{idx}"

        resolved = target.resolve()
        if create:
            resolved.mkdir(parents=True, exist_ok=True)

        _ACTIVE_OUTPUT_DIR = resolved
        _CTX_OUTPUT_DIR.set(resolved)
        os.environ[ENV_PROJECT_DIR_KEY] = str(resolved)
        return resolved


def get_output_dir(ensure_exists: bool = True) -> Path:
    """
    Returns the active project workspace directory (preferring per-task ContextVar
    for concurrency safety, falling back to env/global only outside a task context).
    """
    ctx_dir = _CTX_OUTPUT_DIR.get()
    if ctx_dir is not None:
        path = ctx_dir
    else:
        env_val = os.environ.get(ENV_PROJECT_DIR_KEY, "").strip()
        if env_val:
            path = Path(env_val)
        elif _ACTIVE_OUTPUT_DIR is not None:
            path = _ACTIVE_OUTPUT_DIR
        else:
            path = ROOT_DIR / "output"

    if ensure_exists:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_artifact_path(filename: str, ensure_exists: bool = True) -> Path:
    """Returns a path inside the active project workspace (e.g. final_prd.md)."""
    return get_output_dir(ensure_exists=ensure_exists) / filename


_SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".cs",
    ".html", ".css", ".vue", ".svelte", ".swift", ".dart", ".sql", ".php", ".rb",
}
_IGNORED_DIRS = {"node_modules", ".git", "dist", "build", "target", "__pycache__", ".venv", "venv"}
_IGNORED_FILES = {"tailwind.config.js", "postcss.config.js", "vite.config.js", "vite.config.ts", "eslint.config.js"}


def count_source_files() -> int:
    """
    Counts real source-code files in the active project workspace.
    Folders, markdown drafts, lock files and tooling configs do NOT count, so a
    project that only has empty directories (or just docs/config) returns 0.
    """
    root = get_output_dir(ensure_exists=False)
    if not root.exists():
        return 0
    total = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _IGNORED_DIRS for part in p.relative_to(root).parts):
            continue
        if p.name in _IGNORED_FILES:
            continue
        if p.suffix.lower() in _SOURCE_EXTENSIONS:
            total += 1
    return total


def list_project_dirs() -> List[Path]:
    """Lists all project directories under ``projects/`` sorted by most recently modified."""
    if not PROJECTS_DIR.exists():
        return []
    dirs = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs
