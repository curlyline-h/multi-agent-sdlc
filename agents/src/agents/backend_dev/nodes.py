"""
Backend Developer Agent — Node Functions

Flow:
  pop_task → write_code → lint_code → run_tests → mark_task_complete → pop_task
  (loops write_code if lint_code or run_tests fail)
"""
from pathlib import Path
from typing import Any
from langchain_core.prompts import PromptTemplate
from agents.src.shared.llm import get_llm, llm_tool_invoke_with_retry, execute_tool_calls, run_tool_loop_with_json_fallback
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from dotenv import load_dotenv
import json
import os
import re
import subprocess

load_dotenv()

from agents.src.agents.backend_dev.state import BackendDevState
from agents.src.agents.backend_dev.tools import (
    code_linter,
    run_unit_tests,
    db_schema_inspector
)
from agents.src.shared.tools import (
    list_directory, 
    fetch_server_logs, 
    run_terminal_command,
    read_file_range,
    semantic_code_search,
    write_file,
    replace_file_content,
    search_web,
    rag_search
)

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_ROOT_DIR = Path(__file__).resolve().parents[4]

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
_llm = get_llm(temperature=0.1, max_tokens=8192)

# ---------------------------------------------------------------------------
# 1. Pop Task Node
# ---------------------------------------------------------------------------
def pop_task_node(state: BackendDevState) -> dict:
    """
    Pulls the next uncompleted task from the queue.
    """
    tasks = list(state.workflow_tasks)
    
    if not tasks:
        # Queue is empty
        return {"current_task": None}
        
    next_task = tasks.pop(0)
    
    return {
        "workflow_tasks": tasks,
        "current_task": next_task,
        "linter_errors": "",
        "test_failures": "",
        "iteration_count": 0
    }

from agents.src.shared.schemas import GeneratedFile, CodeGenerationResponse

from agents.src.shared.context import build_codebase_context

def _get_codebase_summary() -> str:
    return build_codebase_context(
        allowed_extensions={
            ".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".css", ".json",
            ".java", ".kt", ".go", ".rs", ".cs", ".xml", ".gradle",
        },
        preferred_keywords=("backend", "api", "server", "route", "model", "db", "controller", "main"),
    )

# ---------------------------------------------------------------------------
# 2. Write Code Node
# ---------------------------------------------------------------------------
def write_code_node(state: BackendDevState) -> dict:
    """
    Writes the application code and the unit tests for the current task.
    """
    prompt_path = _PROMPTS_DIR / "backend_dev.txt"
    prompt = PromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    
    # We load the current db schema from output/db/init.sql if it exists
    db_schema = "No database schema found."
    from agents.src.shared.workspace import get_output_dir
    db_file = get_output_dir(ensure_exists=False) / "db" / "init.sql"
    if db_file.exists():
        db_schema = db_file.read_text(encoding="utf-8")
        
    existing_code = _get_codebase_summary()
        
    formatted = prompt.format(
        design_doc=state.final_design_doc,
        tasks=str(state.current_task),
        db_changes=db_schema,
        existing_code=existing_code,
        linter_errors=state.linter_errors or 'No errors',
        test_failures=state.test_failures or 'No failures',
    )
    
    formatted += "\n\nCRITICAL: You MUST output ONLY valid JSON matching this schema:\n{\n  \"terminal_commands\": [\"cmd1\", \"cmd2\"],\n  \"files\": [\n    {\"path\": \"src/file.ts\", \"content\": \"raw code\"}\n  ]\n}\n\nDo not use markdown wrappers unless wrapping the entire JSON block in ```json ... ```. Your output MUST parse successfully via json.loads()."
    
    from langchain_core.tools import tool
    from agents.src.shared.tools import run_terminal_command
        
    # Bind tools to the LLM
    tools_list = [write_file, read_file_range, semantic_code_search, search_web, run_terminal_command, db_schema_inspector, replace_file_content, list_directory, fetch_server_logs, code_linter, run_unit_tests, rag_search]
    llm_with_tools = _llm.bind_tools(tools_list)
    
    # Inform the agent it can execute terminal commands, read chunks or search existing code
    formatted += "\n\nPREFERRED WORKFLOW: Use the `write_file(file_path, content)` tool to write each source file directly to disk one by one (e.g. `write_file('src/main/java/.../GameEngine.java', ...)` or `write_file('pom.xml', ...)`). This avoids JSON truncation. After writing all files with `write_file`, output `{\"terminal_commands\": [...], \"files\": []}` as your final JSON."
    formatted += "\n\nNote: You have FULL generic terminal access via `run_terminal_command`, `write_file` to create/overwrite files, `replace_file_content` for small edits, `read_file_range` to view files, and `list_directory` to explore paths."
    formatted += "\n\nCRITICAL RULE: DO NOT use tool calling for your final JSON output. You MUST output your final JSON directly in your message text response, surrounded by ```json ... ```. If you wrap your final JSON in a tool call (like 'json' or 'CodeGenerationResponse'), it will crash the system."
    if os.name == 'nt':
        formatted += "\n\nOS RULE: The terminal is Windows cmd.exe. DO NOT use Linux commands like `mkdir -p`, `rm -rf`, or `touch`. Use Windows equivalents (e.g., `mkdir` without `-p` to create directories, `del /s /q` or `rmdir /s /q` for deletion). `mkdir` automatically creates intermediate directories in cmd."
        
    messages: list[Any] = [
        SystemMessage(content=formatted),
        HumanMessage(content="Start your implementation. You can execute shell commands with `run_terminal_command`, search the codebase with `semantic_code_search`, read files with `read_file_range`, edit files with `replace_file_content`, list directories with `list_directory`, and fetch server logs with `fetch_server_logs`. When done, output the final code JSON as plain text.")
    ]
    
    generated_code_dump = []
    
    try:
        final_content: str = run_tool_loop_with_json_fallback(
            _llm,
            tools_list,
            messages,
            agent_name="Backend Dev",
            max_turns=12,
            nudge_after_turn=8,
        )

        # Now parse final_content as the code JSON response
        from agents.src.shared.workspace import get_output_dir
        output_dir = get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        import re
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', final_content, re.DOTALL)
        content: str
        if match:
            content = str(match.group(1))
        else:
            start = final_content.find('{')
            end = final_content.rfind('}')
            if start != -1 and end != -1:
                content = final_content[start:end+1]
            else:
                content = final_content
                
        def _parse_json_robust(text: str) -> dict:
            try:
                return json.loads(text, strict=False)
            except Exception:
                pass
            cleaned = re.sub(r',\s*([}\]])', r'\1', text)
            try:
                return json.loads(cleaned, strict=False)
            except Exception:
                pass
            cleaned_ctrl = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
            return json.loads(cleaned_ctrl, strict=False)

        data = _parse_json_robust(content)
        
        # Execute terminal commands
        for cmd in data.get("terminal_commands", []):
            # Only block infinite blocking dev server daemons that hang execution
            DAEMON_SERVER_PREFIXES = [
                "npm run dev", "npm run start", "npm start", "node server", 
                "python manage.py runserver", "flask run", "uvicorn", "npx next dev"
            ]
            
            if any(cmd.strip().startswith(prefix) for prefix in DAEMON_SERVER_PREFIXES):
                print(f"Backend Dev skipped (infinite server daemon): {cmd}")
                generated_code_dump.append(f"Skipped background server daemon: {cmd}")
                continue
            
            if cmd.startswith("npm install") and "--legacy-peer-deps" not in cmd:
                cmd += " --legacy-peer-deps"
            
            # Auto-fix Windows cmd.exe incompatible commands
            if os.name == 'nt':
                if cmd.strip().startswith("mkdir -p "):
                    cmd = cmd.replace("mkdir -p ", "mkdir ")
                elif cmd.strip().startswith("rm -rf "):
                    cmd = cmd.replace("rm -rf ", "rmdir /s /q ")
            
            print(f"Backend Dev executing: {cmd}")
            try:
                res = subprocess.run(cmd, shell=True, cwd=str(output_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=200)
                try:
                    from backend.telemetry import broadcast_tool_call
                    broadcast_tool_call("execute_command", cmd, event_type="TERMINAL_COMMAND", payload_extra={"command": cmd, "stdout": res.stdout or "", "stderr": res.stderr or "", "exit_code": res.returncode})
                except Exception:
                    pass
                if(res.returncode!=0):
                    generated_code_dump.append(f"Command {cmd} failed with output {res.stdout}\n")
                else:
                    generated_code_dump.append(f"Command '{cmd}' succeeded.\n")
            except subprocess.TimeoutExpired:
                print(f"Command '{cmd}' timed out. Skipping.")
                generated_code_dump.append(f"Command '{cmd}' timed out.")
    
        # Write files
        for f in data.get("files", []):
            file_content = f.get("content", "")
            
            if f.get("path", "").endswith(".json"):
                file_content = re.sub(r'//.*?\n', '\n', file_content)
                file_content = re.sub(r'/\*.*?\*/', '', file_content, flags=re.DOTALL)
            
            clean_path = f.get("path", "").lstrip("/")
            if clean_path.startswith("output/"): clean_path = clean_path[7:]
            file_path = output_dir / clean_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(file_content, encoding="utf-8")
            print(f"Backend Dev wrote: {os.path.relpath(file_path, _ROOT_DIR)}")
            generated_code_dump.append(f"File: {os.path.relpath(file_path, _ROOT_DIR)} written.")
            try:
                from backend.telemetry import broadcast_tool_call
                rel_p = str(file_path.relative_to(output_dir))
                broadcast_tool_call("create_file", rel_p, event_type="FILE_CHANGE", payload_extra={"path": rel_p, "action": "CREATED", "diff": f"+ Created file {rel_p}"})
            except Exception:
                pass
            
    except Exception as e:
        print(f"Raw JSON parsing failed: {e}")
        generated_code_dump.append(f"Error generating code: {e}")
        
    return {
        "current_code_draft": "\n\n".join(generated_code_dump),
        "iteration_count": state.iteration_count + 1
    }

# ---------------------------------------------------------------------------
# 3. Lint Code Node
# ---------------------------------------------------------------------------
def lint_code_node(state: BackendDevState) -> dict:
    """
    Runs a stack-aware build/compile verification against the generated codebase
    (Maven, Gradle, Node/TypeScript, Python py_compile, Go, Rust, .NET).
    """
    from agents.src.shared.workspace import count_source_files
    from agents.src.shared.verifier import verify_project_build

    if count_source_files() == 0:
        msg = "No backend source files were generated yet (only folders/docs exist). Use `write_file` to create the actual source code files."
        print(f"Backend Dev lint: FAILED ({msg})")
        return {"linter_errors": msg}

    passed, errors = verify_project_build(label="Backend Dev")
    if passed:
        print("Backend Dev build check: PASSED")
        return {"linter_errors": ""}
    print(f"Backend Dev build check: FAILED\n{errors}")
    return {"linter_errors": errors}

# ---------------------------------------------------------------------------
# 4. Run Tests Node
# ---------------------------------------------------------------------------
def run_tests_node(state: BackendDevState) -> dict:
    """
    Runs the unit tests against the generated code.
    """
    result = run_unit_tests.invoke({"test_file_path": "backend/tests/test_temp.py"})
    return {"test_failures": "" if result == "TESTS_PASSED" else result}

# ---------------------------------------------------------------------------
# 5. Mark Task Complete Node
# ---------------------------------------------------------------------------
def mark_task_complete_node(state: BackendDevState) -> dict:
    """
    If tests pass, the task is marked as completed and added to the done pile.
    Extracts the generated code into backend_file_changes.
    """
    completed = list(state.completed_tasks)
    changes = list(state.backend_file_changes)
    
    if state.current_task:
        completed.append(state.current_task)
        if state.current_code_draft:
            changes.append({
                "task_title": state.current_task.get("title", "Unknown"),
                "status": "completed"
            })
        
    return {
        "completed_tasks": completed,
        "current_task": None,
        "backend_file_changes": changes
    }

# ---------------------------------------------------------------------------
# 6. GitHub Push Node
# ---------------------------------------------------------------------------
def push_to_github_node(state: BackendDevState) -> dict:
    """Pushes the current output directory to GitHub with a descriptive commit."""
    from agents.src.shared.github import push_to_github
    current_task = state.current_task or {}
    context = {
        "project_name":      getattr(state, "project_name", "") or "",
        "task_title":        current_task.get("title", "") if isinstance(current_task, dict) else "",
        "task_description":  current_task.get("description", "") if isinstance(current_task, dict) else "",
        "completed_tasks":   list(getattr(state, "completed_task_titles", []) or []),
        "files_changed":     list(getattr(state, "final_file_changes", []) or []),
        "scope":             "api",
        "linter_clean":      not bool(getattr(state, "linter_errors", "")),
    }
    res = push_to_github(state.github_repo_name or "", "Backend Developer Agent", context=context)
    return {"active_pr_number": res.get("pr_number", 0)}
