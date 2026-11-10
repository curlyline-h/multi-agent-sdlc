"""
Security Agent — MCP and Internal Tools

Tools for static application security testing (SAST), Software Composition Analysis (SCA),
and Jira ticket integration for zero-days.
"""
from agents.src.shared.tools import tool
import os
import subprocess
from pathlib import Path

# Re-export generic terminal tool so nodes can import it from this package
from agents.src.shared.tools import run_terminal_command, get_output_dir  # noqa: F401

_ROOT_DIR = Path(__file__).resolve().parents[5]

@tool
def run_sast_scanner(path: str = "") -> str:
    """
    Runs a Static Application Security Testing (SAST) tool.
    Detects Python (bandit) or Node (basic grep for secrets as a fallback).
    """
    output_dir = get_output_dir()
    
    if (output_dir / "package.json").exists():
        # A simple SAST alternative for node if eslint-plugin-security isn't installed
        cmd = "npx --yes @nodesecure/cli --ci"
        fallback = "grep -ir 'password\\|secret\\|token' . | head -n 20"
    else:
        cmd = "bandit -r . -f txt"
        fallback = "grep -ir 'password\\|secret\\|token' . | head -n 20"
        
    try:
        res = subprocess.run(cmd, shell=True, cwd=str(output_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        return f"SAST_SCAN_COMPLETE:\n{res.stdout[-2000:]}"
    except Exception:
        # Fallback to basic secrets grep if scanner not installed
        try:
            res = subprocess.run(fallback, shell=True, cwd=str(output_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            return f"SAST_SCAN (Fallback Secrets Check):\n{res.stdout}"
        except Exception as e:
            return f"SAST_SCAN_FAILED: {e}"

@tool
def check_dependencies(path: str = "") -> str:
    """
    Runs a Software Composition Analysis (SCA) tool (e.g., npm audit).
    """
    output_dir = get_output_dir()
    
    if (output_dir / "package.json").exists():
        cmd = "npm audit --audit-level=high"
    elif (output_dir / "requirements.txt").exists():
        cmd = "pip-audit -r requirements.txt"
    else:
        return "DEPENDENCY_SCAN_SKIPPED: No package.json or requirements.txt found."
        
    try:
        res = subprocess.run(cmd, shell=True, cwd=str(output_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if res.returncode == 0:
            return "DEPENDENCY_SCAN_PASSED: 0 vulnerabilities found."
        else:
            return f"DEPENDENCY_SCAN_WARNINGS:\n{res.stdout[-2000:]}"
    except Exception as e:
        return f"DEPENDENCY_SCAN_FAILED: {e}"

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
