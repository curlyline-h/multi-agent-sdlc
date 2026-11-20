"""
Reviewer Agent — MCP and Internal Tools

Tools for static analysis and GitHub Pull Request integration.
"""
from agents.src.shared.tools import tool
import os
import requests
import subprocess
from pathlib import Path

# Re-export generic terminal tool so nodes can import it from this package
from agents.src.shared.tools import run_terminal_command  # noqa: F401

from agents.src.shared.workspace import get_output_dir


_SKIP_DIRS = {"node_modules", ".git", "target", "build", "dist", ".next", "__pycache__", ".venv", "venv"}
_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".go", ".rs", ".cs", ".cpp", ".h", ".sql", ".html", ".css"}


@tool
def run_complexity_analysis() -> str:
    """
    Cross-platform static analysis & git diff summary over the generated project workspace.
    Computes file counts, line counts, large files (>400 LOC), unfinished TODO/FIXME markers,
    and git diff statistics if a git repository is initialized.
    """
    import re
    from agents.src.shared.proc import run_command_safe

    output_dir = get_output_dir()
    if not output_dir.exists():
        return "ANALYSIS_FAILED: No output directory found to analyze."

    try:
        total_files = 0
        total_lines = 0
        large_files: list[str] = []
        placeholder_hits: list[str] = []

        for p in sorted(output_dir.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in _CODE_EXTS:
                continue
            try:
                rel = p.relative_to(output_dir)
            except ValueError:
                continue
            if _SKIP_DIRS.intersection(rel.parts):
                continue

            total_files += 1
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            lines = text.splitlines()
            loc = len(lines)
            total_lines += loc
            if loc > 400:
                large_files.append(f"{rel} ({loc} LOC)")

            for idx, line in enumerate(lines, 1):
                if re.search(r"\b(TODO|FIXME|NotImplementedError|pass\s*#\s*todo)\b", line, re.IGNORECASE):
                    placeholder_hits.append(f"{rel}:{idx}: {line.strip()[:80]}")
                    if len(placeholder_hits) >= 15:
                        break

        git_summary = "No git repository initialized in workspace."
        if (output_dir / ".git").exists():
            rc, out, _, timed_out = run_command_safe("git status --short", output_dir, timeout=10)
            rc_d, out_d, _, _ = run_command_safe("git diff --stat HEAD", output_dir, timeout=10)
            parts = []
            if not timed_out and rc == 0 and out.strip():
                parts.append("Working Tree Status:\n" + out.strip()[:800])
            if rc_d == 0 and out_d.strip():
                parts.append("Git Diff Stat:\n" + out_d.strip()[:800])
            if parts:
                git_summary = "\n\n".join(parts)

        report_lines = [
            f"ANALYSIS_SUCCESS: {total_files} source files analyzed ({total_lines} total LOC).",
            f"Large files (>400 LOC): {', '.join(large_files) if large_files else 'None'}",
            f"Unfinished TODO/FIXME markers ({len(placeholder_hits)}): "
            + ("\n  - " + "\n  - ".join(placeholder_hits) if placeholder_hits else "None"),
            f"\n{git_summary}",
        ]
        return "\n".join(report_lines)
    except Exception as e:
        return f"ANALYSIS_FAILED: {e}"

@tool
def leave_pr_comment(github_repo_name: str, pr_number: int, comment_body: str, is_approved: bool) -> str:
    """
    Submits a code review to a GitHub Pull Request via the GitHub API.
    If is_approved is false, requests changes.
    """
    if not github_repo_name or not pr_number:
        return "ERROR: github_repo_name or pr_number is missing."
        
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        # Fallback to local markdown file if no token
        review_file = get_output_dir() / "CODE_REVIEW.md"
        status = "APPROVED" if is_approved else "CHANGES REQUESTED"
        content = f"# PR #{pr_number} Review\n**Status:** {status}\n\n{comment_body}\n"
        review_file.write_text(content, encoding="utf-8")
        return f"SUCCESS: Token missing, wrote review to {review_file.name}"
        
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Get user login
    user_login = requests.get("https://api.github.com/user", headers=headers).json().get("login")
    
    event = "APPROVE" if is_approved else "REQUEST_CHANGES"
    url = f"https://api.github.com/repos/{user_login}/{github_repo_name}/pulls/{pr_number}/reviews"
    
    payload = {
        "body": comment_body,
        "event": event
    }
    
    res = requests.post(url, headers=headers, json=payload)
    if res.status_code == 200:
        return f"SUCCESS: PR #{pr_number} review submitted as {event}."
    else:
        return f"FAILED to submit PR review: {res.status_code} {res.text}"

@tool
def merge_pull_request(github_repo_name: str, pr_number: int, commit_message: str) -> str:
    """
    Merges a GitHub Pull Request into main via the GitHub API.
    Call this ONLY AFTER the code has been thoroughly reviewed and approved.
    """
    if not github_repo_name or not pr_number:
        return "ERROR: github_repo_name or pr_number is missing."
        
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return "ERROR: GITHUB_TOKEN not found in environment."
        
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Get user login
    user_login = requests.get("https://api.github.com/user", headers=headers).json().get("login")
    
    url = f"https://api.github.com/repos/{user_login}/{github_repo_name}/pulls/{pr_number}/merge"
    payload = {
        "commit_title": f"Merge PR #{pr_number}",
        "commit_message": commit_message,
        "merge_method": "squash"
    }
    
    res = requests.put(url, headers=headers, json=payload)
    if res.status_code == 200:
        return f"SUCCESS: PR #{pr_number} has been merged into main."
    else:
        return f"FAILED to merge PR: {res.status_code} {res.text}"
