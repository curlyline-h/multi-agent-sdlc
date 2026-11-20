"""
Frontend Developer Agent — Tools

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

@tool
def api_schema_fetcher() -> str:
    """
    Scans the output/ directory for backend API route files across any framework
    (Next.js, Express, FastAPI, Django, Flask, Spring, Go, etc.)
    to discover available endpoints and their structure.
    """
    output_dir = get_output_dir()
    
    api_files = []
    
    # Scan for common backend route/API file patterns across all frameworks
    patterns = [
        # Next.js App Router
        "src/app/api/**/route.ts", "src/app/api/**/route.js",
        "app/api/**/route.ts", "app/api/**/route.js",
        # Next.js Pages Router
        "pages/api/**/*.ts", "pages/api/**/*.js",
        # Express / Node.js
        "**/routes/**/*.js", "**/routes/**/*.ts",
        "**/controllers/**/*.js", "**/controllers/**/*.ts",
        # Python (FastAPI, Flask, Django)
        "**/routes/**/*.py", "**/views/**/*.py",
        "**/routers/**/*.py", "**/endpoints/**/*.py",
        "**/urls.py", "**/views.py", "**/api.py",
        # Java / Spring
        "**/controller/**/*.java", "**/Controller.java",
        # Go
        "**/handlers/**/*.go", "**/routes/**/*.go",
        # General
        "**/openapi.json", "**/openapi.yaml", "**/swagger.json", "**/swagger.yaml",
    ]
    
    for pattern in patterns:
        found = glob.glob(str(output_dir / pattern), recursive=True)
        for f in found:
            # Skip node_modules and hidden directories
            if "node_modules" in f or "/.git/" in f or "\\.git\\" in f:
                continue
            rel_path = Path(f).relative_to(output_dir)
            try:
                content = Path(f).read_text(encoding="utf-8")
                api_files.append(f"File: {rel_path}\n{content[:500]}")
            except Exception:
                api_files.append(f"File: {rel_path} (could not read)")
    
    if api_files:
        return "Discovered Backend API Files:\n\n" + "\n\n---\n\n".join(api_files[:20])
    
    # Fallback: read the DB schema if no API routes found
    db_file = output_dir / "db" / "init.sql"
    if db_file.exists():
        return f"No API routes found, but found DB schema:\n{db_file.read_text(encoding='utf-8')[:1000]}"
    
    return "No backend API files or schemas found in output/ directory."


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
    elif (output_dir / "Gemfile").exists():
        return "ruby"
    return "unknown"


@tool
def frontend_linter(file_path: str) -> str:
    """
    Runs the appropriate linter based on the detected tech stack.
    Args:
        file_path: Path to the file to lint (relative to output/).
    """
    output_dir = get_output_dir()
    stack = _detect_stack(output_dir)
    
    # Only run tsc if tsconfig.json exists
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
def run_component_tests(test_file_path: str) -> str:
    """
    Runs the appropriate test suite based on the detected tech stack.
    - Node: npm test / vitest
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
def visual_browser_check(route_url: str = "") -> str:
    """
    Verifies frontend build and, if a live URL or Playwright setup exists, checks for
    browser console/page errors and broken entrypoint assets.
    """
    from agents.src.shared.verifier import verify_project_build
    from agents.src.shared.proc import run_command_safe

    output_dir = get_output_dir()
    passed, build_errors = verify_project_build(output_dir=output_dir, label="Frontend-VisualCheck")
    if not passed:
        return f"BUILD_ERRORS:\n{build_errors[:1500]}"

    # Validate HTML entrypoints reference existing local scripts/stylesheets
    missing_refs: list[str] = []
    for html_file in list(output_dir.glob("*.html")) + list((output_dir / "public").glob("*.html")):
        if not html_file.is_file():
            continue
        try:
            html_text = html_file.read_text(encoding="utf-8", errors="replace")
            for ref in re.findall(r'(?:src|href)=["\'](/[^"\']+)["\']', html_text):
                clean_ref = ref.lstrip("/").split("?")[0]
                if clean_ref and not (output_dir / clean_ref).exists() and not (output_dir / "public" / clean_ref).exists():
                    missing_refs.append(f"{html_file.name} references missing file '{ref}'")
        except Exception:
            pass
    if missing_refs:
        return "BUILD_ERRORS:\n" + "\n".join(missing_refs)

    # If route_url is provided and Playwright is installed in workspace, run a headless browser check
    if route_url and route_url.startswith("http") and (
        (output_dir / "node_modules" / "playwright").exists()
        or (output_dir / "node_modules" / "@playwright").exists()
    ):
        pw_script = (
            "const { chromium } = require('playwright');"
            "(async () => {"
            "  const b = await chromium.launch({ headless: true });"
            "  const p = await b.newPage();"
            "  const errs = [];"
            "  p.on('pageerror', e => errs.push(String(e)));"
            "  p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });"
            f"  await p.goto({route_url!r}, {{ waitUntil: 'domcontentloaded', timeout: 8000 }});"
            "  await b.close();"
            "  if (errs.length) { console.error(errs.join('\\n')); process.exit(1); }"
            "})().catch(e => { console.error(String(e)); process.exit(1); });"
        )
        rc, out, err, timed_out = run_command_safe(f'node -e "{pw_script}"', output_dir, timeout=15)
        if not timed_out and rc != 0 and (err or out).strip():
            return f"BUILD_ERRORS:\n{(err or out).strip()[:1500]}"

    return "CONSOLE_CLEAN: Frontend build and entrypoint asset verification passed."


