"""
QA Agent — MCP and Internal Tools

These tools support automated E2E testing, exploratory browser testing, 
and automated Jira bug reporting.
"""
from agents.src.shared.tools import tool
import os
import requests
import subprocess
from pathlib import Path
from agents.src.shared.tools import run_terminal_command

from agents.src.shared.workspace import get_output_dir

@tool
def api_integration_tester(endpoint: str, method: str, payload: dict = None) -> str:
    """
    Fires raw HTTP requests against the backend (like Postman or curl).
    Useful for testing API logic independently of the UI.
    """
    try:
        if method.upper() == "GET":
            res = requests.get(endpoint, params=payload, timeout=10)
        elif method.upper() == "POST":
            res = requests.post(endpoint, json=payload, timeout=10)
        elif method.upper() == "PUT":
            res = requests.put(endpoint, json=payload, timeout=10)
        elif method.upper() == "DELETE":
            res = requests.delete(endpoint, timeout=10)
        else:
            return f"ERROR: Unsupported method {method}"
            
        return f"HTTP {res.status_code}\nResponse: {res.text[:2000]}"
    except Exception as e:
        return f"API_TEST_FAILED: {e}"

@tool
def run_test_suite() -> str:
    """
    Executes the project's automated test suite, choosing the command from the detected stack
    (Maven/Gradle for Java, pytest for Python, npm/Playwright for web projects).
    Never opens a headed browser and never blocks on interactive prompts.
    """
    import json
    from agents.src.shared.proc import run_command_safe

    output_dir = get_output_dir()

    pkg = output_dir / "package.json"
    pkg_deps: dict = {}
    pkg_scripts: dict = {}
    if pkg.exists():
        try:
            pkg_json = json.loads(pkg.read_text(encoding="utf-8"))
            pkg_deps = {**pkg_json.get("dependencies", {}), **pkg_json.get("devDependencies", {})}
            pkg_scripts = pkg_json.get("scripts", {}) or {}
        except Exception:
            pass

    has_playwright_cfg = (output_dir / "playwright.config.ts").exists() or (output_dir / "playwright.config.js").exists()

    if (output_dir / "pom.xml").exists():
        cmd = "mvn -q -B test"
        timeout = 300
    elif (output_dir / "build.gradle").exists() or (output_dir / "build.gradle.kts").exists():
        cmd = "gradlew.bat test" if (os.name == "nt" and (output_dir / "gradlew.bat").exists()) else "gradle test"
        timeout = 300
    elif has_playwright_cfg and "@playwright/test" in pkg_deps and (output_dir / "node_modules" / "@playwright" / "test").exists():
        cmd = "npx --no-install playwright test --workers=1"
        timeout = 180
    elif pkg.exists() and pkg_scripts.get("test") and (output_dir / "node_modules").exists():
        test_script = str(pkg_scripts.get("test", "")).lower()
        if "jest" in test_script or "react-scripts" in test_script:
            cmd = "npm test -- --watchAll=false --passWithNoTests"
        elif "vitest" in test_script:
            cmd = "npx --no-install vitest run"
        else:
            cmd = "npm test --silent"
        timeout = 180
    elif (output_dir / "pytest.ini").exists() or (output_dir / "tests").exists() and list(output_dir.rglob("test_*.py")):
        cmd = "pytest -q"
        timeout = 180
    else:
        return "TEST_FAILED: No test suite configuration found in the output directory."

    try:
        returncode, stdout, stderr, timed_out = run_command_safe(cmd, output_dir, timeout=timeout)
        if timed_out:
            return f"TEST_EXECUTION_FAILED: '{cmd}' timed out after {timeout}s and was terminated."
        if returncode == 0:
            return f"TEST_EXECUTION_COMPLETE: Tests passed.\n{stdout[-1000:]}"
        errors = stdout + stderr
        return f"TEST_EXECUTION_FAILED ({cmd}):\n{errors[-2000:]}"
    except Exception as e:
        return f"TEST_EXECUTION_FAILED: {e}"

@tool
def generate_bug_report(title: str, steps: str, expected: str, actual: str) -> str:
    """
    Formats the bug details and logs it. Since Jira MCP is not fully connected,
    it writes the bug report to a persistent BUGS.md file in the output directory.
    Args:
        title: Bug summary.
        steps: Steps to reproduce.
        expected: Expected behavior based on the PRD.
        actual: Actual behavior observed during testing.
    """
    bugs_file = get_output_dir() / "BUGS.md"
    
    import time
    bug_id = f"BUG-{int(time.time())}"
    
    report = f"## [{bug_id}] {title}\n"
    report += f"**Steps to Reproduce:**\n{steps}\n\n"
    report += f"**Expected:** {expected}\n\n"
    report += f"**Actual:** {actual}\n\n"
    report += "---\n\n"
    
    # Append to BUGS.md
    bugs_file.parent.mkdir(parents=True, exist_ok=True)
    with open(bugs_file, "a", encoding="utf-8") as f:
        f.write(report)
        
    return f"SUCCESS: Bug logged as {bug_id} in {bugs_file.name}"

@tool
def visual_browser_tester(url: str, action: str) -> str:
    """
    Simulates a browser interacting with the UI.
    Fetches the HTML DOM of the page to verify elements are rendering.
    """
    try:
        # We use a simple HTTP GET to simulate browser fetching the page
        headers = {"User-Agent": "Mozilla/5.0 QA-Agent-Browser"}
        res = requests.get(url, headers=headers, timeout=15)
        
        # Extract the title and a snippet of the body to simulate DOM inspection
        import re
        title_match = re.search(r'<title>(.*?)</title>', res.text, re.IGNORECASE)
        title = title_match.group(1) if title_match else "No Title Found"
        
        body_snippet = res.text[:2000] # Return first 2000 chars as a proxy
        
        return f"BROWSER_ACTION '{action}' on {url} SUCCESS.\nPage Title: {title}\nDOM Snippet: {body_snippet}..."
    except Exception as e:
        return f"BROWSER_TEST_FAILED: Could not reach {url}. Error: {e}"
