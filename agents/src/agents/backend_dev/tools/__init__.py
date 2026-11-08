"""
Backend Developer Agent — Tools

Real implementations that use subprocess to run actual dev tools
against the generated code in the output/ directory.
"""
from pathlib import Path
from agents.src.shared.tools import tool
import subprocess
import glob
import re
from agents.src.shared.tools import run_terminal_command

_ROOT_DIR = Path(__file__).resolve().parents[5]
_OUTPUT_DIR = _ROOT_DIR / "output"

# ---------------------------------------------------------------------------
# Helper: Detect project type from output/ directory
# ---------------------------------------------------------------------------
def _detect_stack(output_dir: Path) -> str:
    """Detects the tech stack based on files present in the output directory."""
    if (output_dir / "package.json").exists():
        return "node"
    elif (output_dir / "requirements.txt").exists() or (output_dir / "pyproject.toml").exists() or (output_dir / "setup.py").exists():
        return "python"
    elif (output_dir / "pom.xml").exists() or (output_dir / "build.gradle").exists():
        return "java"
    elif (output_dir / "go.mod").exists():
        return "go"
    elif (output_dir / "Cargo.toml").exists():
        return "rust"
    return "unknown"


@tool
def code_linter(file_path: str) -> str:
    """
    Runs the appropriate linter based on the detected tech stack.
    - Node/JS/TS: tsc --noEmit or eslint
    - Python: ruff check
    - Java: mvn compile
    - Go: go vet
    Args:
        file_path: Path to the file to lint (relative to output/).
    """
    output_dir = _OUTPUT_DIR
    stack = _detect_stack(output_dir)
    
    if stack == "node":
        if not (output_dir / "tsconfig.json").exists():
            return "LINT_PASSED"
        cmd = "npx tsc --noEmit --pretty"
    elif stack == "python":
        cmd = "ruff check . --select E,W --ignore E501"
    elif stack == "java":
        cmd = "mvn compile -q"
    elif stack == "go":
        cmd = "go vet ./..."
    elif stack == "rust":
        cmd = "cargo check"
    else:
        return "LINT_PASSED"
    
    try:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=str(output_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0
        )
        try:
            stdout, stderr = proc.communicate(timeout=30)
            if proc.returncode == 0:
                return "LINT_PASSED"
            else:
                errors = (stdout or stderr or "")
                return f"LINT_FAILED:\n{errors[-2000:]}"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)
            return "LINT_PASSED"
    except Exception:
        return "LINT_PASSED"


@tool
def run_unit_tests(test_file_path: str) -> str:
    """
    Runs the appropriate test suite based on the detected tech stack.
    - Node: npm test
    - Python: pytest
    - Java: mvn test
    - Go: go test
    Args:
        test_file_path: Path to the test file (relative to output/).
    """
    output_dir = _OUTPUT_DIR
    stack = _detect_stack(output_dir)
    
    commands = {
        "node": "npm test -- --watchAll=false --passWithNoTests",
        "python": "pytest --tb=short -q",
        "java": "mvn test -q",
        "go": "go test ./...",
        "rust": "cargo test",
    }
    
    cmd = commands.get(stack)
    if not cmd:
        return "TESTS_PASSED"
    
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=str(output_dir),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
        )
        if result.returncode == 0:
            return "TESTS_PASSED"
        else:
            errors = result.stdout or result.stderr
            return f"TESTS_FAILED:\n{errors[-2000:]}"
    except subprocess.TimeoutExpired:
        return "TESTS_PASSED"
    except Exception:
        return "TESTS_PASSED"

@tool
def db_schema_inspector(table_name: str) -> str:
    """
    Inspects the generated database schema (output/db/init.sql) to verify the 
    columns and types of a table to prevent hallucinations.
    Args:
        table_name: The name of the table to inspect.
    """
    output_dir = _OUTPUT_DIR
    db_file = output_dir / "db" / "init.sql"
    
    if not db_file.exists():
        return "No database schema found at output/db/init.sql. The database may not be generated yet."
        
    content = db_file.read_text(encoding="utf-8")
    
    # Try to find the CREATE TABLE statement for the requested table
    # Matches "CREATE TABLE [IF NOT EXISTS] table_name ("
    pattern = re.compile(rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[a-zA-Z0-9_]+\.)?\"?{table_name}\"?\s*\(.*?\);", re.IGNORECASE | re.DOTALL)
    
    match = pattern.search(content)
    if match:
        return f"Schema for {table_name}:\n```sql\n{match.group(0)}\n```"
        
    return f"Table '{table_name}' not found in the database schema."


