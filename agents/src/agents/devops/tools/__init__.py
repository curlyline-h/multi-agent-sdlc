"""
DevOps Agent — MCP and Internal Tools

These tools interact with Docker and GitHub.
"""
from agents.src.shared.tools import tool
import subprocess
import requests
import time
from pathlib import Path
from agents.src.shared.tools import run_terminal_command

from agents.src.shared.workspace import get_output_dir

@tool
def validate_iac_config(iac_code: str, config_type: str = "auto") -> str:
    """
    Validates infrastructure-as-code files before attempting deployment.
    Runs `docker-compose config -q` to catch YAML/schema errors.
    Args:
        iac_code: The raw configuration string.
        config_type: e.g. "docker-compose", "terraform", "kubernetes"
    """
    output_dir = get_output_dir()
    
    # Check if docker-compose exists
    if not (output_dir / "docker-compose.yml").exists() and not (output_dir / "docker-compose.yaml").exists():
        return "VALIDATION_PASSED: No docker-compose file found to validate."
        
    from agents.src.shared.proc import run_command_safe
    rc, stdout, stderr, timed_out = run_command_safe("docker compose config -q", output_dir, timeout=30)
    if timed_out:
        return "VALIDATION_FAILED: 'docker compose config -q' timed out after 30s."
    if rc == 0:
        return "VALIDATION_PASSED: The configuration is syntactically correct."
    return f"VALIDATION_FAILED: {(stderr or stdout)[-2000:]}"

@tool
def run_deployment(plan: str) -> str:
    """
    Executes the deployment against the physical environment via Docker.
    Note: Usually the graph handles this automatically.
    """
    from agents.src.shared.proc import run_command_safe
    output_dir = get_output_dir()
    rc, stdout, stderr, timed_out = run_command_safe("docker compose up -d --build", output_dir, timeout=180)
    if timed_out:
        return "DEPLOYMENT_FAILED: 'docker compose up -d --build' timed out after 180s."
    if rc == 0:
        return f"DEPLOYMENT_SUCCESS: Containers started.\n{stdout[-4000:]}"
    return f"DEPLOYMENT_FAILED: {(stderr or stdout)[-4000:]}"

@tool
def health_check_ping(target_url: str) -> str:
    """
    Pings the live endpoint to ensure the deployed service is actually running
    and returning HTTP 200 OK. Will retry up to 5 times.
    """
    for attempt in range(1, 6):
        try:
            res = requests.get(target_url, timeout=5)
            if res.status_code == 200:
                return f"HEALTH_CHECK_PASSED: {target_url} responded with HTTP 200 OK."
            else:
                return f"HEALTH_CHECK_FAILED: {target_url} responded with HTTP {res.status_code}."
        except requests.ConnectionError:
            if attempt < 5:
                time.sleep(2)
            else:
                return f"HEALTH_CHECK_FAILED: Could not connect to {target_url} after 5 attempts."
        except Exception as e:
            return f"HEALTH_CHECK_FAILED: {e}"
            
    return f"HEALTH_CHECK_FAILED: Unknown error pinging {target_url}."

@tool
def push_github_actions(ci_cd_scripts: str) -> str:
    """
    Writes CI/CD pipeline scripts to the .github/workflows directory.
    The main GitHub Push node will handle actually pushing it.
    """
    workflows_dir = get_output_dir() / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    
    (workflows_dir / "ci.yml").write_text(ci_cd_scripts, encoding="utf-8")
    return "SUCCESS: CI/CD pipelines written to .github/workflows/ci.yml"
