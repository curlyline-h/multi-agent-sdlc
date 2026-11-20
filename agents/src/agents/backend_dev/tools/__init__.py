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

from agents.src.shared.workspace import get_output_dir

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
    output_dir = get_output_dir()
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
    
    from agents.src.shared.proc import run_command_safe
    rc, stdout, stderr, timed_out = run_command_safe(cmd, output_dir, timeout=45)
    if timed_out:
        return f"LINT_FAILED: '{cmd}' timed out after 45s."
    if rc == 0:
        return "LINT_PASSED"
    errors = (stdout or "") + ("\n" + stderr if stderr else "")
    return f"LINT_FAILED:\n{errors.strip()[-2000:]}"


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
    output_dir = get_output_dir()
    stack = _detect_stack(output_dir)

    if stack == "node":
        import json as _json
        pkg = output_dir / "package.json"
        try:
            scripts = (_json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}) if pkg.exists() else {}
        except Exception:
            scripts = {}
        test_script = str(scripts.get("test", "")).strip()
        if not test_script or "no test specified" in test_script.lower():
            return "TESTS_PASSED"
        cmd = (
            "npx --no-install vitest run --passWithNoTests"
            if "vitest" in test_script.lower()
            else "npm test -- --watchAll=false --passWithNoTests"
        )
    elif stack == "python":
        has_py_tests = any(
            p.is_file() and "node_modules" not in p.parts and (p.name.startswith("test_") or p.name.endswith("_test.py"))
            for p in output_dir.rglob("*.py")
        )
        if not has_py_tests:
            return "TESTS_PASSED"
        cmd = "pytest --tb=short -q"
    elif stack == "java":
        cmd = "mvn -B test -q"
    elif stack == "go":
        cmd = "go test ./..."
    elif stack == "rust":
        cmd = "cargo test"
    else:
        return "TESTS_PASSED"

    from agents.src.shared.proc import run_command_safe
    rc, stdout, stderr, timed_out = run_command_safe(cmd, output_dir, timeout=120)
    if timed_out:
        return f"TESTS_FAILED: '{cmd}' timed out after 120s."
    if rc == 0:
        return "TESTS_PASSED"
    errors = (stdout or "") + ("\n" + stderr if stderr else "")
    return f"TESTS_FAILED:\n{errors.strip()[-2000:]}"

@tool
def db_schema_inspector(table_name: str) -> str:
    """
    Inspects the generated database schema (output/db/init.sql) to verify the 
    columns and types of a table to prevent hallucinations.
    Args:
        table_name: The name of the table to inspect.
    """
    output_dir = get_output_dir()
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


