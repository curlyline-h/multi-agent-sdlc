"""
Shared Agent Tools — Generic terminal execution tool.
"""
import subprocess
from pathlib import Path
from langchain_core.tools import tool as _lc_tool
import functools
import json

def agent_tool(*args, **kwargs):
    """
    A wrapper around LangChain's @tool decorator that automatically
    broadcasts tool executions to the UI.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*f_args, **f_kwargs):
            try:
                from backend.telemetry import broadcast_tool_call
                arg_str = json.dumps(f_kwargs, default=str)
                # Avoid broadcasting run_terminal_command here because it has its own specialized broadcast logic
                if func.__name__ != "run_terminal_command":
                    broadcast_tool_call(func.__name__, arg_str[:250])
            except Exception:
                pass
            try:
                return func(*f_args, **f_kwargs)
            except Exception as tool_exc:
                return f"Tool error in {func.__name__}: {tool_exc}"
        return _lc_tool(*args, **kwargs)(wrapper)
        
    if len(args) == 1 and callable(args[0]) and not kwargs:
        func = args[0]
        args = ()
        return decorator(func)
    return decorator

tool = agent_tool

import os

_ROOT_DIR = Path(__file__).resolve().parents[3]
_OUTPUT_DIR = _ROOT_DIR / "output"


def get_output_dir() -> Path:
    """
    Returns the active scenario's dedicated working directory `output/<scenario_id>/`
    when `USE_SCENARIO_SUBDIR=1` or when `output/<scenario_id>` exists, falling back to `output/`.
    """
    scen_id = os.environ.get("ACTIVE_SCENARIO_ID", "").strip()
    base = _ROOT_DIR / "output"
    if scen_id and (os.environ.get("USE_SCENARIO_SUBDIR") == "1" or (base / scen_id).exists()):
        out = base / scen_id
    else:
        out = base
    out.mkdir(parents=True, exist_ok=True)
    return out


def _clean_rel_path(p: str) -> str:
    clean_p = (p or "").strip().lstrip("/")
    scen_id = os.environ.get("ACTIVE_SCENARIO_ID", "").strip()
    if clean_p == "output" or (scen_id and clean_p == f"output/{scen_id}"):
        return ""
    if scen_id and clean_p.startswith(f"output/{scen_id}/"):
        clean_p = clean_p[len(f"output/{scen_id}/"):]
    elif clean_p.startswith("output/"):
        clean_p = clean_p[7:]
    if scen_id and clean_p.startswith(f"{scen_id}/"):
        clean_p = clean_p[len(f"{scen_id}/"):]
    return clean_p


@tool
def write_file(file_path: str, content: str) -> str:
    """
    Creates or overwrites a file in the project's output directory with the given content.
    Parent directories are created automatically.
    Args:
        file_path: Relative path of the file inside the project output directory (e.g. 'src/main.py', 'db/init.sql').
        content: Full text content to write into the file.
    """
    out_dir = get_output_dir()
    clean_p = _clean_rel_path(file_path)
    if not clean_p:
        return "Error: file_path cannot be empty."
    target = out_dir / clean_p
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        try:
            from backend.telemetry import broadcast_tool_call
            broadcast_tool_call(
                "create_file",
                clean_p,
                event_type="FILE_CHANGE",
                payload_extra={"path": clean_p, "action": "CREATED", "diff": f"+ Wrote {clean_p} ({len(content)} chars)"},
            )
        except Exception:
            pass
        return f"SUCCESS: Wrote {len(content)} characters to {clean_p}."
    except Exception as e:
        return f"Error writing file {clean_p}: {e}"


@tool
def run_terminal_command(command: str) -> str:
    """
    Executes any generic shell / terminal command inside the project's output directory.
    Args:
        command: The exact shell command line string to execute (e.g. 'npm install axios', 'python script.py').
    """
    out_dir = get_output_dir()
    
    # Non-blocking non-interactive auto-fix for npm install
    if command.startswith("npm install") and "--legacy-peer-deps" not in command:
        command += " --legacy-peer-deps"
    
    # Auto-fix Windows cmd.exe incompatible commands
    if os.name == 'nt':
        if command.strip().startswith("mkdir -p "):
            command = command.replace("mkdir -p ", "mkdir ")
        elif command.strip().startswith("rm -rf "):
            command = command.replace("rm -rf ", "rmdir /s /q ")
        
    try:
        res = subprocess.run(
            command,
            shell=True,
            cwd=str(out_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180
        )
        stdout = res.stdout.strip()
        stderr = res.stderr.strip()
        
        try:
            from backend.telemetry import broadcast_tool_call
            
            broadcast_tool_call(
                "run_terminal_command",
                command,
                event_type="TERMINAL_COMMAND",
                payload_extra={
                    "command": command,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": res.returncode
                }
            )
        except Exception:
            pass

        if res.returncode == 0:
            output = stdout or stderr or "Command completed with exit code 0."
            return f"COMMAND_SUCCESS ({command}):\n{output[-2000:]}"
        else:
            output = stderr or stdout or "Command failed."
            return f"COMMAND_FAILED (exit code {res.returncode}):\n{output[-2000:]}"
    except subprocess.TimeoutExpired:
        return f"COMMAND_TIMEOUT: Command '{command}' timed out after 180s."
    except Exception as e:
        return f"COMMAND_ERROR: {e}"


@tool
def list_directory(path: str = "", depth: int = 1) -> str:
    """
    Lists the files and directories in the given path within the project output directory.
    Use this to explore the project structure and find exact file paths for imports or edits.
    Args:
        path: Directory path relative to output/ (e.g., '', 'src', 'src/components'). Use '' for root.
        depth: Optional directory listing depth (default 1).
    """
    out_dir = get_output_dir()
    clean_p = _clean_rel_path(path)
    target = (out_dir / clean_p) if clean_p else out_dir
    if not target.exists():
        return f"Error: Directory '{path}' does not exist."
    if not target.is_dir():
        return f"Error: '{path}' is a file, not a directory."
        
    try:
        items = list(target.iterdir())
        if not items:
            return f"Directory '{path}' is empty."
            
        dirs = [d.name + "/" for d in items if d.is_dir() and d.name not in (".git", "node_modules")]
        files = [f.name for f in items if f.is_file()]
        
        result = f"Contents of {path or 'root'}:\n"
        result += "\n".join(sorted(dirs) + sorted(files))
        return result
    except Exception as e:
        return f"Error listing directory: {e}"


@tool
def fetch_server_logs(lines: int = 100) -> str:
    """
    Fetches the last N lines of the server daemon logs (output/server.log).
    Since 'npm run dev' and 'fastapi run' are skipped by run_terminal_command to prevent blocking,
    devops or dev agents can configure daemons to write to server.log, and use this tool to debug runtime errors.
    """
    log_file = get_output_dir() / "server.log"
    if not log_file.exists():
        return "No server.log file found. Ensure your server command redirects output to server.log (e.g. 'npm run dev > server.log 2>&1 &')."
        
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            
        if not all_lines:
            return "server.log is empty."
            
        start = max(0, len(all_lines) - lines)
        return "--- Last {} lines of server.log ---\n".format(lines) + "".join(all_lines[start:])
    except Exception as e:
        return f"Error fetching logs: {e}"


import glob
@tool
def replace_file_content(file_path: str, target_string: str, replacement_string: str) -> str:
    """
    Finds exactly `target_string` in the file and replaces it with `replacement_string`.
    Use this for surgical bug fixes instead of rewriting the entire file.
    Note: `target_string` must match EXACTLY (including whitespace) and must appear exactly once in the file.
    Args:
        file_path: Path to the file (relative to output/).
        target_string: The exact string block to replace.
        replacement_string: The string block to insert in its place.
    """
    out_dir = get_output_dir()
    clean_p = _clean_rel_path(file_path)
    target = out_dir / clean_p
    if not target.exists():
        return f"Error: File {file_path} does not exist."
        
    try:
        content = target.read_text(encoding="utf-8")
        count = content.count(target_string)
        if count == 0:
            return "Error: target_string not found in file. Ensure exact whitespace matching."
        if count > 1:
            return f"Error: target_string found {count} times. Please provide a larger block of context to make it unique."
            
        new_content = content.replace(target_string, replacement_string)
        target.write_text(new_content, encoding="utf-8")
        return f"SUCCESS: Content replaced in {file_path}."
    except Exception as e:
        return f"Error modifying file: {e}"



@tool
def read_file_range(file_path: str, start_line: int = 1, end_line: int = 200) -> str:
    """
    Reads a specific line range from a file (1-indexed) in the output directory
    to prevent fetching massive files.
    Args:
        file_path: Path to the file (relative to output/).
        start_line: The line number to start reading from (inclusive).
        end_line: The line number to end reading (inclusive).
    """
    out_dir = get_output_dir()
    clean_p = _clean_rel_path(file_path)
    target = out_dir / clean_p
    if not target.exists():
        return f"Error: File {file_path} does not exist."
        
    try:
        with open(target, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        start = max(1, start_line)
        end = min(total_lines, end_line)
        
        if end < start:
            return f"Error: Invalid range {start}-{end}."
            
        if end - start > 500:
            return "Error: Cannot read more than 500 lines at once."
            
        selected = lines[start-1:end]
        return f"--- File: {file_path} (Lines {start}-{end} of {total_lines}) ---\n" + "".join(selected)
    except Exception as e:
        return f"Error reading file: {e}"



@tool
def semantic_code_search(query: str, path: str = "") -> str:
    """
    Searches previously written code to find utility functions or router patterns.
    Uses basic keyword matching across the output/ directory.
    Args:
        query: What to search for (e.g., 'auth', 'database connection').
        path: Optional subdirectory relative to output/ to restrict search.
    """
    output_dir = get_output_dir()
    clean_sub = _clean_rel_path(path)
    search_root = (output_dir / clean_sub) if clean_sub and (output_dir / clean_sub).exists() else output_dir
    matches = []
    
    # Common code file extensions
    extensions = ["*.py", "*.ts", "*.js", "*.java", "*.go", "*.rs", "*.tsx", "*.jsx", "*.sql", "*.yaml", "*.json"]
    
    for ext in extensions:
        for f in glob.glob(str(search_root / "**" / ext), recursive=True):
            if "node_modules" in f or "/.git/" in f or "\\.git\\" in f or ".next" in f:
                continue
            
            try:
                content = Path(f).read_text(encoding="utf-8")
                # Simple case-insensitive search
                if query.lower() in content.lower():
                    rel_path = Path(f).relative_to(output_dir)
                    # Extract a snippet around the match
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if query.lower() in line.lower():
                            start = max(0, i - 2)
                            end = min(len(lines), i + 3)
                            snippet = "\n".join(lines[start:end])
                            matches.append(f"File: {rel_path}\nMatch:\n{snippet}\n")
                            break # Just get first match per file to keep it short
            except Exception:
                pass
                
    if not matches:
        return f"No code found matching '{query}' in the output directory."
        
    return f"Search Results for '{query}':\n\n" + "\n---\n".join(matches[:5])


def _get_rag_pipeline():
    from agents.src.rag import RAGPipeline
    return RAGPipeline()


@tool
def rag_search(query: str, k: int = 5) -> str:
    """
    Search the internal knowledge base for past architecture decision records (ADRs),
    previous system designs, and uploaded technical documentation.
    """
    pipeline = _get_rag_pipeline()
    results = pipeline.hybrid_search(query=query, k=k)
    if not results:
        return "No relevant documents found in the internal knowledge base."
    chunks = [
        f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
        for doc in results
    ]
    return "\n\n---\n\n".join(chunks)


# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Schema Validator (Internal)
# ---------------------------------------------------------------------------



from agents.src.shared.llm import safe_web_search
@tool
def search_web(query: str, path: str = "") -> str:
    """Performs a web search to find current information or documentation."""
    return safe_web_search(query)
