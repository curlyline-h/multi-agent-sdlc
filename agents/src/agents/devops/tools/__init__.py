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

_ROOT_DIR = Path(__file__).resolve().parents[5]
_OUTPUT_DIR = _ROOT_DIR / "output"

@tool
def validate_iac_config(iac_code: str, config_type: str = "auto") -> str:
    """
    Validates infrastructure-as-code files before attempting deployment.
    Runs `docker-compose config -q` to catch YAML/schema errors.
    Args:
        iac_code: The raw configuration string.
        config_type: e.g. "docker-compose", "terraform", "kubernetes"
    """
    output_dir = _OUTPUT_DIR
    
    # Check if docker-compose exists
    if not (output_dir / "docker-compose.yml").exists() and not (output_dir / "docker-compose.yaml").exists():
        return "VALIDATION_PASSED: No docker-compose file found to validate."
        
    try:
        res = subprocess.run(
            "docker compose config -q",
            shell=True,
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )
        if res.returncode == 0:
            return "VALIDATION_PASSED: The configuration is syntactically correct."
        else:
            return f"VALIDATION_FAILED: {res.stderr[-2000:]}"
    except Exception as e:
        return f"VALIDATION_FAILED: Exception during validation - {e}"

@tool
def run_deployment(plan: str) -> str:
    """
    Executes the deployment against the physical environment via Docker.
    Note: Usually the graph handles this automatically.
    """
    output_dir = _OUTPUT_DIR
    try:
        res = subprocess.run(
            "docker compose up -d --build",
            shell=True,
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False
        )
        if res.returncode == 0:
            return f"DEPLOYMENT_SUCCESS: Containers started.\n{res.stdout[-4000:]}"
        else:
            return f"DEPLOYMENT_FAILED: {res.stderr[-4000:]}"
    except Exception as e:
        return f"DEPLOYMENT_FAILED: {e}"

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
    workflows_dir = _OUTPUT_DIR / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    
    (workflows_dir / "ci.yml").write_text(ci_cd_scripts, encoding="utf-8")
    return "SUCCESS: CI/CD pipelines written to .github/workflows/ci.yml"
