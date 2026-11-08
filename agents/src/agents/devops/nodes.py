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
from agents.src.shared.llm import get_llm, llm_tool_invoke_with_retry
from pydantic import BaseModel, Field
from typing import List
import subprocess
import os
import requests

class GeneratedFile(BaseModel):
    path: str = Field(description="The relative path to save the file to, e.g. docker-compose.yml")
    content: str = Field(description="The full raw code content of the file")

class CodeGenerationResponse(BaseModel):
    terminal_commands: List[str] = Field(default_factory=list, description="List of shell commands to execute")
    files: List[GeneratedFile] = Field(description="List of files to generate or update")

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_ROOT_DIR = Path(__file__).resolve().parents[4]

_llm = get_llm(temperature=0.1, max_tokens=4000)

def _get_codebase_summary() -> str:
    output_dir = _ROOT_DIR / "output"
    if not output_dir.exists():
        return "No generated code found yet."
        
    code_blocks = []
    omitted_files = []
    allowed_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".css", ".json", ".md", ".html", ".yml", ".yaml", ".toml"}
    ignored_dirs = {"node_modules", ".git", ".next", "dist", "build"}
    
    MAX_TOTAL_CHARS = 40000
    current_total_chars = 0
    
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            if any(part in ignored_dirs for part in path.parts):
                continue
            if path.suffix in allowed_extensions:
                rel_path = path.relative_to(_ROOT_DIR)
                if current_total_chars >= MAX_TOTAL_CHARS:
                    omitted_files.append(str(rel_path))
                    continue
                    
                try:
                    content = path.read_text(encoding="utf-8")
                    if len(content) > 5000:
                        content = content[:5000] + "\n... [TRUNCATED] ..."
                    block = f"File: {rel_path}\n```\n{content}\n```"
                    code_blocks.append(block)
                    current_total_chars += len(block)
                except Exception as e:
                    code_blocks.append(f"File: {rel_path} (Error: {e})")
                    
    if not code_blocks and not omitted_files:
        return "No files generated yet."
        
    res = "\n\n".join(code_blocks)
    if omitted_files:
        res += "\n\n### Omitted files due to context limits:\n" + "\n".join(f"- {f}" for f in omitted_files)
    return res

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
    llm_with_tools = _llm.bind_tools(tools_list)
    
    messages = [
        SystemMessage(content="You are a Principal DevOps Engineer. You write deployment configs and scripts."),
        HumanMessage(content=formatted)
    ]
    
    # ReAct Loop
    turn_limit = 15
    for turn in range(turn_limit):
        try:
            response = llm_tool_invoke_with_retry(llm_with_tools, messages, agent_name="DevOps")
        except Exception as e:
            if "tool_calls" in str(e).lower() or "invalid_json" in str(e).lower():
                import ast
                error_str = str(e)
                start_idx = error_str.find("'{")
                end_idx = error_str.rfind("}'") + 2
                if start_idx != -1 and end_idx != -1:
                    if end_idx == -1 or end_idx <= start_idx:
                        end_idx = error_str.rfind("'")
                    try:
                        raw_fg = error_str[start_idx:end_idx].replace("\\n", "\n").replace("\\'", "'")
                        failed_gen = json.loads(raw_fg, strict=False)
                        args = failed_gen.get("arguments", {})
                        class DummyResponse:
                            content = json.dumps(args) if isinstance(args, dict) else str(args)
                            tool_calls = []
                        response = DummyResponse()
                    except Exception:
                        raise e
                else:
                    raise e
            else:
                raise e
                
        messages.append(response)
        
        if not getattr(response, "tool_calls", []):
            break
            
        # Check if it accidentally provided the JSON block alongside tool calls
        if response.content and ("```json" in response.content or "terminal_commands" in response.content):
            break
            
        tool_map = {tool.name: tool for tool in tools_list}
        for tool_call in response.tool_calls:
            name = tool_call["name"]
            print(f"Agent calling tool: {name} with args {tool_call['args']}")
            if name in tool_map:
                result = tool_map[name].invoke(tool_call["args"])
            else:
                result = f"Error: Tool {name} not found."
            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    generated_dump = []
    deployment_cmds = []
    
    try:
        # Find the content containing the JSON
        content = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str) and ("```json" in msg.content or "terminal_commands" in msg.content):
                content = msg.content
                break
        if not content:
            content = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
            
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
        if json_match:
            parsed = json.loads(json_match.group(1) if '```' in content else json_match.group(0))
        else:
            parsed = json.loads(content)
            
        parsed_response = CodeGenerationResponse(**parsed)
        
        output_dir = _ROOT_DIR / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Terminal commands
        deployment_cmds = parsed_response.terminal_commands
        if deployment_cmds:
            generated_dump.append("Planned deployment commands:\n" + "\n".join(f"- {c}" for c in deployment_cmds))
        
        # Files
        for f in parsed_response.files:
            file_path = output_dir / f.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f.content, encoding="utf-8")
            print(f"DevOps wrote: output/{f.path}")
            generated_dump.append(f"File: output/{f.path}\n{f.content}")
            
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
    res = push_to_github(state.github_repo_name, "DevOps Agent", context=context)
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
    """
    user_response = interrupt({
        "type": "deployment_approval",
        "plan": state.deployment_plan,
        "message": (
            "CRITICAL: The DevOps Agent is ready to deploy your application. "
            "Please review the deployment plan (Docker/Terraform scripts). "
            "Approve to proceed with actual deployment, or provide feedback."
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
    output_dir = _ROOT_DIR / "output"
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
                res = subprocess.run(cmd, shell=True, cwd=str(output_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
                if res.returncode == 0:
                    logs.append(f"SUCCESS: {cmd}\n{res.stdout[-4000:]}")
                else:
                    logs.append(f"FAILED: {cmd}\n{(res.stderr or res.stdout)[-4000:]}")
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
    next_task = tasks.pop(0)
    return {"workflow_tasks": tasks, "current_task": next_task}

def mark_task_complete_node(state: DevOpsState) -> dict:
    return {"current_task": None}
