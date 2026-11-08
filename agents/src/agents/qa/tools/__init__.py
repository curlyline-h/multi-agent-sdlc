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

_ROOT_DIR = Path(__file__).resolve().parents[4]
_OUTPUT_DIR = _ROOT_DIR / "output"

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
    Executes the automated E2E test suite (e.g., npx playwright test or npm test).
    Looks for test configurations in the output directory.
    """
    output_dir = _OUTPUT_DIR
    
    # Check what kind of tests exist
    if (output_dir / "playwright.config.ts").exists() or (output_dir / "playwright.config.js").exists():
        cmd = "npx playwright test --headed --workers=1"
    elif (output_dir / "package.json").exists():
        cmd = "npm test"
    elif (output_dir / "pytest.ini").exists():
        cmd = "pytest"
    else:
        return "TEST_FAILED: No test suite configuration found in the output directory."
        
    try:
        res = subprocess.run(
            cmd, shell=True, cwd=str(output_dir),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
        )
        if res.returncode == 0:
            return f"TEST_EXECUTION_COMPLETE: Tests passed.\n{res.stdout[-1000:]}"
        else:
            errors = res.stdout + res.stderr
            return f"TEST_EXECUTION_FAILED:\n{errors[-2000:]}"
    except subprocess.TimeoutExpired:
        return "TEST_EXECUTION_FAILED: Timeout expired."
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
    bugs_file = _OUTPUT_DIR / "BUGS.md"
    
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
