"""
DevOps Agent — Node Functions

Flow:
  generate_deployment_plan → validate_plan 
  → [loop if invalid] → approve_deployment (Interrupt)
  → [loop if rejected] → execute_deployment → push_to_github → verify_health
"""
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from langgraph.types import interrupt

from agents.src.agents.devops.state import DevOpsState
from typing import Dict, Any
from agents.src.agents.devops.tools import (
    validate_iac_config,
    run_deployment,
    health_check_ping,
    push_github_actions,
    run_terminal_command,
)
from agents.src.shared.tools import (
    semantic_code_search,
    read_file_range,
    replace_file_content,
    list_directory,
    fetch_server_logs,
    search_web,
    rag_search,
)

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
from agents.src.shared.llm import get_llm, run_tool_loop_with_json_fallback
from pydantic import BaseModel, Field
from typing import List
import subprocess
import os
import requests

from agents.src.shared.schemas import GeneratedFile, CodeGenerationResponse

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_ROOT_DIR = Path(__file__).resolve().parents[4]

_llm = get_llm(temperature=0.1, max_tokens=4000)

from agents.src.shared.context import build_codebase_context

def _get_codebase_summary() -> str:
    return build_codebase_context(
        preferred_keywords=("docker", "package.json", "requirements", "pyproject", "main", "index", "env"),
    )

# ---------------------------------------------------------------------------
# 1. Generate Deployment Plan Node
# ---------------------------------------------------------------------------
def generate_deployment_plan_node(state: DevOpsState) -> dict:
    """
    Reads the final architecture design document.
    Generates Dockerfiles, docker-compose.yml, and CI/CD pipelines.
    """
    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
    import re
    import json
    
    prompt_path = _PROMPTS_DIR / "devops.txt"
    prompt = PromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    
    existing_code = _get_codebase_summary()
    
    formatted = prompt.format(
        design=state.final_design_doc,
        existing_code=existing_code,
        feedback=state.deployment_feedback or "None.",
        linter=state.iac_validation_notes or "None."
    )
    
    formatted += "\n\nNote: You have FULL terminal and file system access. You can call `run_terminal_command`, `semantic_code_search`, `read_file_range`, `replace_file_content`, `list_directory`, `fetch_server_logs`, `search_web`, and `rag_search` to inspect the workspace or look up documentation. Gather whatever context you need first. Once ready, output your final payload wrapped EXACTLY in a ```json block matching the CodeGenerationResponse schema. DO NOT output anything else after the JSON block."
    
    import os
    if os.name == 'nt':
        formatted += "\n\nOS RULE: The terminal is Windows cmd.exe. DO NOT use Linux commands like `mkdir -p`, `rm -rf`, or `touch`. Use Windows equivalents (e.g., `mkdir` without `-p` to create directories, `del /s /q` or `rmdir /s /q` for deletion). `mkdir` automatically creates intermediate directories in cmd."
        
    tools_list = [run_terminal_command, semantic_code_search, read_file_range, replace_file_content, list_directory, fetch_server_logs, search_web, rag_search, validate_iac_config, run_deployment, health_check_ping, push_github_actions]
    messages: list[Any] = [
        SystemMessage(content="You are a Principal DevOps Engineer. You write deployment configs and scripts."),
        HumanMessage(content=formatted)
    ]

    generated_dump = []
    deployment_cmds = []

    try:
        content = run_tool_loop_with_json_fallback(
            _llm,
            tools_list,
            messages,
            agent_name="DevOps",
            max_turns=8,
            nudge_after_turn=4,
            nudge_message=(
                "Stop inspecting files and output your final CodeGenerationResponse JSON now "
                'wrapped in ```json ... ```: {"terminal_commands": [...], "files": [{"path": "...", "content": "..."}]}.'
            ),
        )

        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)

        if json_match:
            parsed = json.loads(json_match.group(1) if '```' in content else json_match.group(0))
        else:
            parsed = json.loads(content)

        parsed_response = CodeGenerationResponse(**parsed)

        from agents.src.shared.workspace import get_output_dir
        output_dir = get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Terminal commands
        deployment_cmds = parsed_response.terminal_commands
        if deployment_cmds:
            generated_dump.append("Planned deployment commands:\n" + "\n".join(f"- {c}" for c in deployment_cmds))

        # Files
        for f in parsed_response.files:
            clean_path = f.path.lstrip("/")
            if clean_path.startswith("output/"):
                clean_path = clean_path[7:]
            file_path = output_dir / clean_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f.content, encoding="utf-8")
            print(f"DevOps wrote: {clean_path}")
            generated_dump.append(f"File: {clean_path}\n{f.content}")
            
    except Exception as e:
        print(f"JSON parsing failed: {e}")
        generated_dump.append(f"Error: {e}")
    
    return {
        "deployment_plan": "\n\n".join(generated_dump),
        "deployment_commands": deployment_cmds,
        "iteration_count": state.iteration_count + 1
    }

# ---------------------------------------------------------------------------
# GitHub Push Node (Deterministic — no LLM involved)
# ---------------------------------------------------------------------------
def push_to_github_node(state: DevOpsState) -> dict:
    """
    Creates a GitHub repo via the API and pushes the output/ directory.
    Only runs if github_repo_name is set in state.
    """
    from agents.src.shared.github import push_to_github
    current_task = state.current_task or {}
    context = {
        "project_name":      getattr(state, "project_name", "") or "",
        "task_title":        current_task.get("title", "Deploy infrastructure & CI/CD") if isinstance(current_task, dict) else "Deploy infrastructure & CI/CD",
        "task_description":  current_task.get("description", "") if isinstance(current_task, dict) else "",
        "completed_tasks":   list(getattr(state, "completed_task_titles", []) or []),
        "files_changed":     [],  # DevOps writes docker-compose, Dockerfile, ci.yml
        "scope":             "infra",
        "linter_clean":      "VALIDATION_PASSED" in (getattr(state, "iac_validation_notes", "") or ""),
    }
    res = push_to_github(state.github_repo_name or "", "DevOps Agent", context=context)
    return {"active_pr_number": res.get("pr_number", 0)}

# ---------------------------------------------------------------------------
# 2. Validate Plan Node
# ---------------------------------------------------------------------------
def validate_plan_node(state: DevOpsState) -> dict:
    """
    Runs the internal validation tool to lint the generated configurations.
    """
    notes = validate_iac_config.invoke({"iac_code": state.deployment_plan, "config_type": "auto"})
    return {"iac_validation_notes": notes}

# ---------------------------------------------------------------------------
# 3. Approve Deployment Node (Interrupt)
# ---------------------------------------------------------------------------
def approve_deployment_node(state: DevOpsState) -> dict:
    """
    Interrupts the graph to present the deployment scripts to the user before
    any physical infrastructure is provisioned or containers are started.
    Warns explicitly if the project build is currently failing.
    """
    from agents.src.shared.verifier import verify_project_build

    build_ok, build_errors = verify_project_build(label="DevOps-Gate")
    warning_banner = ""
    if not build_ok:
        warning_banner = (
            "\n\n⚠️ **WARNING: Project build/compile verification FAILED:**\n"
            f"```\n{build_errors[:1200]}\n```\n"
            "You may want to reject deployment until the build errors are resolved."
        )

    user_response = interrupt({
        "type": "deployment_approval",
        "plan": state.deployment_plan + warning_banner,
        "message": (
            "CRITICAL: The DevOps Agent is ready to deploy your application. "
            "Please review the deployment plan (Docker/Terraform scripts). "
            "Approve to proceed with actual deployment, or provide feedback."
            + warning_banner
        )
    })
    
    if not user_response or str(user_response).strip().lower() in ("approve", "yes", "ok", ""):
        return {"deployment_approved": True, "deployment_feedback": ""}
        
    return {"deployment_approved": False, "deployment_feedback": str(user_response)}

# ---------------------------------------------------------------------------
# 4. Execute Deployment Node
# ---------------------------------------------------------------------------
def execute_deployment_node(state: DevOpsState) -> dict:
    """
    Executes the deployment against the physical environment (Docker/Cloud)
    by running the dynamic commands generated by the DevOps agent.
    """
    from agents.src.shared.workspace import get_output_dir
    output_dir = get_output_dir()
    logs = []
    
    cmds_to_run = getattr(state, "deployment_commands", [])
    if not cmds_to_run:
        return {"deployment_logs": "SUCCESS: No deployment commands provided by the agent."}
        
    for cmd in cmds_to_run:
        print(f"DevOps Executing: {cmd}")
        try:
            # Check for background daemons
            DAEMON_SERVER_PREFIXES = [
                "npm run dev", "npm run start", "npm start", "node server", 
                "python manage.py runserver", "flask run", "uvicorn", "npx next dev", "pm2", "bash start.sh", "start.sh", "docker compose up"
            ]
            
            # Auto-fix Windows cmd.exe incompatible commands
            if os.name == 'nt':
                if cmd.strip().startswith("mkdir -p "):
                    cmd = cmd.replace("mkdir -p ", "mkdir ")
                elif cmd.strip().startswith("rm -rf "):
                    cmd = cmd.replace("rm -rf ", "rmdir /s /q ")
            
            if any(cmd.strip().startswith(prefix) for prefix in DAEMON_SERVER_PREFIXES) and "-d" not in cmd:
                # Background the script if it's a daemon and doesn't already have detached flag
                subprocess.Popen(cmd, shell=True, cwd=str(output_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logs.append(f"SUCCESS: Started daemon '{cmd}' in background.")
            else:
                from agents.src.shared.proc import run_command_safe
                rc, stdout, stderr, timed_out = run_command_safe(cmd, output_dir, timeout=180)
                if timed_out:
                    logs.append(f"FAILED: {cmd} timed out after 180s and was terminated.")
                elif rc == 0:
                    logs.append(f"SUCCESS: {cmd}\n{stdout[-4000:]}")
                else:
                    logs.append(f"FAILED: {cmd}\n{(stderr or stdout)[-4000:]}")
        except Exception as e:
            logs.append(f"Error running {cmd}: {e}")
            
    return {"deployment_logs": "\n\n".join(logs)}

# ---------------------------------------------------------------------------
# 5. Verify Health Node
# ---------------------------------------------------------------------------
def verify_health_node(state: DevOpsState) -> dict:
    """
    Pings the live endpoint to verify the system is running.
    """
    try:
        from agents.src.agents.devops.tools import health_check_ping
        status = health_check_ping.invoke({"target_url": "http://localhost:8080/health"})
    except Exception as e:
        status = f"HEALTH_CHECK_FAILED: {e}"
        
    return {"health_check_status": status}

# ---------------------------------------------------------------------------
# Task Queue Management
# ---------------------------------------------------------------------------
def pop_task_node(state: DevOpsState) -> dict:
    tasks = list(state.workflow_tasks)
    if not tasks:
        return {"current_task": None}
    if len(tasks) > 1:
        combined_titles = "; ".join(t.get("title", "") for t in tasks if isinstance(t, dict))
        combined_desc = "\n".join(t.get("description", "") for t in tasks if isinstance(t, dict))
        merged = {**tasks[0], "title": combined_titles, "description": combined_desc}
        return {"workflow_tasks": [], "current_task": merged}
    next_task = tasks.pop(0)
    return {"workflow_tasks": tasks, "current_task": next_task}

def mark_task_complete_node(state: DevOpsState) -> dict:
    return {"current_task": None}
