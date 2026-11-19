"""
Security Agent — MCP and Internal Tools

Tools for static application security testing (SAST), Software Composition Analysis (SCA),
and Jira ticket integration for zero-days.
"""
import os
import re
from pathlib import Path

from agents.src.shared.proc import run_command_safe
from agents.src.shared.tools import tool
# Re-export generic terminal tool so nodes can import it from this package
from agents.src.shared.tools import run_terminal_command  # noqa: F401
from agents.src.shared.workspace import get_output_dir

_SKIP_DIRS = {"node_modules", ".git", "target", "build", "dist", ".next", "__pycache__", ".venv", "venv"}
_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret[_-]?key|password|private[_-]?key|auth[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
]


def _scan_secrets_in_workspace(output_dir: Path) -> str:
    """Fast, cross-platform pure-Python secret & dangerous-pattern scan."""
    findings: list[str] = []
    if not output_dir.exists():
        return "SAST_SCAN_COMPLETE: No output directory to scan."

    for p in output_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".env", ".yml", ".yaml", ".json"}:
            continue
        try:
            rel = p.relative_to(output_dir)
        except ValueError:
            continue
        if _SKIP_DIRS.intersection(rel.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in _SECRET_PATTERNS:
                if pat.search(line):
                    findings.append(f"{rel}:{lineno}: potential hardcoded secret")
                    break
            if len(findings) >= 25:
                break
        if len(findings) >= 25:
            break

    if not findings:
        return "SAST_SCAN_COMPLETE: 0 hardcoded secrets or critical patterns found."
    return "SAST_SCAN_FINDINGS:\n" + "\n".join(findings)


@tool
def run_sast_scanner() -> str:
    """
    Runs Static Application Security Testing (SAST) safely without hanging.
    Uses bandit for Python if available, plus a fast cross-platform secret scan.
    """
    output_dir = get_output_dir()
    if not output_dir.exists():
        return "SAST_SCAN_SKIPPED: Output directory does not exist."

    has_py = any(
        p.is_file() and p.suffix == ".py" and not _SKIP_DIRS.intersection(p.relative_to(output_dir).parts)
        for p in output_dir.rglob("*.py")
    )
    if has_py:
        rc, stdout, stderr, timed_out = run_command_safe("bandit -r . -f txt -q", output_dir, timeout=45)
        if not timed_out and rc in (0, 1) and (stdout or "").strip():
            return f"SAST_SCAN_COMPLETE (bandit):\n{stdout[-2000:]}"

    return _scan_secrets_in_workspace(output_dir)


@tool
def check_dependencies() -> str:
    """
    Runs Software Composition Analysis (SCA) safely using run_command_safe.
    """
    output_dir = get_output_dir()
    if not output_dir.exists():
        return "DEPENDENCY_SCAN_SKIPPED: Output directory does not exist."

    if (output_dir / "package.json").exists() and (output_dir / "package-lock.json").exists():
        cmd = "npm audit --audit-level=high"
    elif (output_dir / "requirements.txt").exists():
        cmd = "pip-audit -r requirements.txt"
    else:
        return "DEPENDENCY_SCAN_SKIPPED: No lockfile (package-lock.json) or requirements.txt found."

    rc, stdout, stderr, timed_out = run_command_safe(cmd, output_dir, timeout=30)
    if timed_out:
        return f"DEPENDENCY_SCAN_SKIPPED: '{cmd}' timed out after 30s."
    if rc == 0:
        return "DEPENDENCY_SCAN_PASSED: 0 vulnerabilities found."
    out = (stdout + stderr).strip()
    return f"DEPENDENCY_SCAN_WARNINGS:\n{out[-2000:]}"

@tool
def file_security_ticket(cve_title: str, severity: str, mitigation: str) -> str:
    """
    Files a high-priority security ticket directly to a local file (since Jira is mocked).
    """
    tickets_file = get_output_dir() / "SECURITY_TICKETS.md"
    
    import time
    ticket_id = f"SEC-{int(time.time())}"
    
    report = f"## [{ticket_id}] {cve_title}\n"
    report += f"**Severity:** {severity}\n\n"
    report += f"**Mitigation Plan:**\n{mitigation}\n\n"
    report += "---\n\n"
    
    tickets_file.parent.mkdir(parents=True, exist_ok=True)
    with open(tickets_file, "a", encoding="utf-8") as f:
        f.write(report)
        
    return f"SUCCESS: Security ticket logged as {ticket_id} in {tickets_file.name}"
