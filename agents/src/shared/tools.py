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
            return func(*f_args, **f_kwargs)
        return _lc_tool(*args, **kwargs)(wrapper)
        
    if len(args) == 1 and callable(args[0]) and not kwargs:
        func = args[0]
        args = ()
        return decorator(func)
    return decorator

tool = agent_tool

_ROOT_DIR = Path(__file__).resolve().parents[3]
_OUTPUT_DIR = _ROOT_DIR / "output"

@tool
def run_terminal_command(command: str) -> str:
    """
    Executes any generic shell / terminal command inside the project's output directory.
    Args:
        command: The exact shell command line string to execute (e.g. 'npm install axios', 'python script.py').
    """
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Non-blocking non-interactive auto-fix for npm install
    if command.startswith("npm install") and "--legacy-peer-deps" not in command:
        command += " --legacy-peer-deps"
    
    # Auto-fix Windows cmd.exe incompatible commands
    import os
    if os.name == 'nt':
        if command.strip().startswith("mkdir -p "):
            command = command.replace("mkdir -p ", "mkdir ")
        elif command.strip().startswith("rm -rf "):
            command = command.replace("rm -rf ", "rmdir /s /q ")
        
    try:
        res = subprocess.run(
            command,
            shell=True,
            cwd=str(_OUTPUT_DIR),
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
def list_directory(path: str) -> str:
    """
    Lists the files and directories in the given path within the output/ directory.
    Use this to explore the project structure and find exact file paths for imports or edits.
    Args:
        path: Directory path relative to output/ (e.g., '', 'src', 'src/components'). Use '' for root.
    """
    target = _OUTPUT_DIR / path.strip("/")
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
    log_file = _OUTPUT_DIR / "server.log"
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
    target = _OUTPUT_DIR / file_path
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
def read_file_range(file_path: str, start_line: int, end_line: int) -> str:
    """
    Reads a specific line range from a file (1-indexed) in the output directory
    to prevent fetching massive files.
    Args:
        file_path: Path to the file (relative to output/).
        start_line: The line number to start reading from (inclusive).
        end_line: The line number to end reading (inclusive).
    """
    target = _OUTPUT_DIR / file_path
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
def semantic_code_search(query: str) -> str:
    """
    Searches previously written code to find utility functions or router patterns.
    Uses basic keyword matching across the output/ directory.
    Args:
        query: What to search for (e.g., 'auth', 'database connection').
    """
    output_dir = _OUTPUT_DIR
    matches = []
    
    # Common code file extensions
    extensions = ["*.py", "*.ts", "*.js", "*.java", "*.go", "*.rs", "*.tsx", "*.jsx"]
    
    for ext in extensions:
        for f in glob.glob(str(output_dir / "**" / ext), recursive=True):
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
def search_web(query: str) -> str:
    """Performs a web search to find current information or documentation."""
    return safe_web_search(query)
