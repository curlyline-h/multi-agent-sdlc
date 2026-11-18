"""
QA Agent â€” Node Functions

Flow:
  pop_task â†’ generate_test_scripts â†’ execute_tests â†’ analyze_results â†’ mark_task_complete â†’ pop_task
"""
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from agents.src.shared.llm import (
    get_llm,
    llm_invoke_with_retry,
    run_tool_loop_with_json_fallback,
)
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field, AliasChoices
from typing import Dict, Any, List

from agents.src.agents.qa.state import QAState
from agents.src.agents.qa.tools import (
    run_test_suite,
    generate_bug_report,
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

_ROOT_DIR = Path(__file__).resolve().parents[4]

# ---------------------------------------------------------------------------
_llm = get_llm(temperature=0.1, max_tokens=4000)

class BugReport(BaseModel):
    title: str = Field(description="Short, specific summary of the bug â€” include the function/method name and what went wrong")
    steps: str = Field(description="Exact steps to reproduce, including the test name and file")
    expected: str = Field(description="The exact value or behaviour that was expected")
    actual: str = Field(description="The exact error message, stack trace excerpt, or wrong value that was observed")

class TestAnalysis(BaseModel):
    discovered_bugs: List[BugReport] = Field(
        default_factory=list,
        validation_alias=AliasChoices("discovered_bugs", "bugs"),
        description="List of bugs extracted from the test logs. Each must have a specific title and real error details."
    )
    all_tests_passed: bool = Field(
        default=False,
        description="True only if every single test in the suite passed. False if any test failed."
    )

# ---------------------------------------------------------------------------
# 1. Generate Test Scripts Node
# ---------------------------------------------------------------------------
from agents.src.shared.context import build_codebase_context

def _get_codebase_summary() -> str:
    return build_codebase_context(
        allowed_extensions={
            ".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".css", ".json", ".md", ".html",
            ".java", ".kt", ".go", ".rs", ".cs", ".xml", ".gradle",
        },
        preferred_keywords=("test", "spec", "app", "main", "index", "controller", "view"),
    )

# ---------------------------------------------------------------------------
# 1. Generate Test Scripts Node
# ---------------------------------------------------------------------------
def generate_tests_node(state: QAState) -> dict:
    """
    Generates a Playwright test suite using the PRD, Design Doc, and output Codebase.
    """
    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
    import re
    import json

    # Playwright E2E only makes sense for web projects. Desktop/CLI/library projects
    # (e.g. Java Swing) are verified by their own build/test tool in execute_tests_node.
    from agents.src.shared.workspace import get_output_dir as _qa_out_dir
    _od = _qa_out_dir()
    _skip_dirs = {"node_modules", "target", "build", "dist", ".git"}
    _is_web = (_od / "package.json").exists() or any(
        not (_skip_dirs & set(p.relative_to(_od).parts)) for p in _od.rglob("index.html")
    )
    if not _is_web:
        print("[QA Agent] Non-web project detected (no package.json / index.html). Skipping Playwright E2E generation.")
        return {"e2e_test_scripts": ""}
    
    prompt = PromptTemplate.from_template(
        """You are a QA Automation Engineer.
        Write end-to-end (E2E) tests in Playwright (TypeScript).
        
        PRD:
        {prd}
        
        Design Doc:
        {design}
        
        Existing Code Base:
        {existing_code}
        
        Note: You have FULL terminal and file system access. You can call `run_terminal_command`, `semantic_code_search`, `read_file_range`, `replace_file_content`, `list_directory`, `fetch_server_logs`, `search_web`, and `rag_search` to inspect the workspace or look up documentation. Gather whatever context you need first. Once ready, output your final Playwright TypeScript code wrapped EXACTLY in a ```typescript block. DO NOT output anything else after the block. Make sure the tests hit 'http://localhost:3000' (or the relevant port).
        """
    )
    
    import os
    if os.name == 'nt':
        prompt.template += "\nOS RULE: The terminal is Windows cmd.exe. DO NOT use Linux commands like `mkdir -p` or `rm -rf`. Use `mkdir` without `-p`."
        
    existing_code = _get_codebase_summary()
    
    formatted = prompt.format(
        prd=state.prd,
        design=state.final_design_doc,
        existing_code=existing_code
    )
    
    tools_list = [run_terminal_command, semantic_code_search, read_file_range, replace_file_content, list_directory, fetch_server_logs, search_web, rag_search, run_test_suite, generate_bug_report]
    messages: list[Any] = [
        SystemMessage(content="You are a QA Automation Engineer."),
        HumanMessage(content=formatted)
    ]

    try:
        content = run_tool_loop_with_json_fallback(
            _llm,
            tools_list,
            messages,
            agent_name="QA",
            max_turns=6,
            nudge_after_turn=3,
            nudge_message=(
                "Stop inspecting files and output your Playwright TypeScript test suite now "
                "wrapped EXACTLY in a ```typescript ... ``` block."
            ),
            final_fallback_prompt=(
                "STOP calling tools immediately. Output ONLY the Playwright TypeScript test code "
                "wrapped in ```typescript ... ```. Do not include any prose outside the code block."
            ),
            stop_markers=("```typescript", "```ts"),
            require_files_payload=False,
        )
    except Exception as e:
        print(f"[QA Agent] LLM generation failed with error: {e}. Proceeding without E2E script.")
        content = ""
        
    match = re.search(r'```(?:typescript|ts)\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
    if match:
        test_code = match.group(1).strip()
    else:
        # The model never produced a test block (e.g. it only listed directories).
        # Do NOT write tool output / prose into e2e.spec.ts.
        print("[QA Agent] No TypeScript test block produced. Skipping E2E spec generation.")
        return {"e2e_test_scripts": ""}
    
    # Write the test to the active project directory
    from agents.src.shared.workspace import get_output_dir
    output_dir = get_output_dir()
    
    # Ensure tests directory exists
    test_dir = output_dir / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Write the spec file
    test_file = test_dir / "e2e.spec.ts"
    test_file.write_text(test_code, encoding="utf-8")
    
    # Write a basic playwright config if it doesn't exist
    config_file = output_dir / "playwright.config.ts"
    if not config_file.exists():
        config_content = """
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://localhost:3000' },
});
"""
        config_file.write_text(config_content.strip(), encoding="utf-8")
    
    return {"e2e_test_scripts": test_code}

# ---------------------------------------------------------------------------
# 2. Execute Tests Node
# ---------------------------------------------------------------------------
def execute_tests_node(state: QAState) -> dict:
    """
    Verifies the project compiles/builds cleanly first, then runs the automated test suite.
    Any build or test failure is returned so analyze_failures_node routes a fix task
    to the responsible developer agent.
    """
    from agents.src.shared.verifier import verify_project_build

    build_ok, build_errors = verify_project_build(label="QA-Build")
    if not build_ok:
        return {"test_run_output": f"TEST_EXECUTION_FAILED (Build/Compile Error):\n{build_errors}"}

    output = run_test_suite.invoke({})
    return {"test_run_output": output}

# ---------------------------------------------------------------------------
# 3. Analyze Failures Node
# ---------------------------------------------------------------------------
def analyze_failures_node(state: QAState) -> dict:
    """
    Parses the output of the test runner. 
    If failures exist, extracts them into structured bug descriptions,
    logs them, and spawns new workflow tasks to fix them.
    """
    logs = state.test_run_output
    
    if "TEST_FAILED: No test suite configuration found" in logs or "TEST_EXECUTION_COMPLETE: Tests passed" in logs:
        # No bugs to report
        return {
            "discovered_bugs": [],
            "all_tests_passed": True,
            "new_workflow_tasks": []
        }
        
    prompt = PromptTemplate.from_template(
        """You are the Lead QA Automation Agent.
        Analyze the following test runner logs and identify all distinct bugs or test failures.
        
        Test Logs:
        {logs}
        
        Extract each failure into a structured bug report. If there are no failures, return an empty list and set all_tests_passed to true.
        
        CRITICAL: You MUST output ONLY valid JSON matching this exact schema:
        {{
          "all_tests_passed": false,
          "bugs": [
            {{
              "title": "Short title",
              "steps": "Steps to reproduce",
              "expected": "Expected behavior",
              "actual": "Actual error/behavior"
            }}
          ]
        }}
        """
    )
    
    formatted = prompt.format(logs=logs)
    try:
        response = llm_invoke_with_retry(_llm, formatted, label="QA-Analyze", structured_schema=TestAnalysis)
    except Exception as e:
        print(f"[QA Agent] Structured LLM parsing failed: {e}. Falling back to default bug report.")
        response = TestAnalysis(
            discovered_bugs=[
                BugReport(
                    title="Test Execution Failure",
                    steps="Run test suite",
                    expected="All tests pass cleanly",
                    actual=logs[:500] if logs else "Tests failed"
                )
            ],
            all_tests_passed=False
        )
    
    new_tasks = []
    import time
    
    # Smart role routing based on failing file paths, stack, and error details.
    # Never route failed test/build runs back to 'qa' — route to the agent that can fix the code.
    def _route_bug(bug: BugReport) -> str:
        text = f"{bug.title} {bug.actual} {bug.steps}".lower()
        if any(k in text for k in ["sql", "migration", "schema", "alembic", "postgres", "sqlite", "database"]):
            return "database_engineer"
        if any(k in text for k in ["docker", "dockerfile", "compose", "ci/cd", "github actions", "terraform", "deploy"]):
            return "devops"
        if any(k in text for k in [
            "component", "render", "ui", "css", "html", "dom", "canvas", "style", "layout",
            "tsx", "jsx", "view", "panel", "frame", "swing", "jframe", "jpanel", "awt",
            "frontend", "next", "react", "vite", "tailwind",
        ]):
            return "frontend"
        return "backend"

    # For each bug, log it using the tool and create a workflow task
    base_ts = int(time.time())
    for idx, bug in enumerate(response.discovered_bugs):
        # 1. Log bug to BUGS.md
        generate_bug_report.invoke({
            "title": bug.title,
            "steps": bug.steps,
            "expected": bug.expected,
            "actual": bug.actual
        })

        # 2. Spawn task for Dispatcher (short unique tag ensures re-try fixes are not skipped as already completed)
        new_tasks.append({
            "id": f"task-bugfix-{base_ts}-{idx}",
            "title": f"Fix QA Bug: {bug.title} (#{base_ts % 10000}-{idx})",
            "description": (
                "A build or test error was discovered during QA verification. Resolve the root cause and verify the build passes.\n\n"
                f"Steps:\n{bug.steps}\n\nExpected:\n{bug.expected}\n\nActual:\n{bug.actual}"
            ),
            "assignee_role": _route_bug(bug),
            "dependencies": [],
            "priority": 1 # High priority
        })
        
    return {
        "discovered_bugs": [bug.model_dump() for bug in response.discovered_bugs],
        "all_tests_passed": response.all_tests_passed,
        "new_workflow_tasks": new_tasks
    }

# ---------------------------------------------------------------------------
# Task Queue Management
# ---------------------------------------------------------------------------
def pop_task_node(state: QAState) -> dict:
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

def mark_task_complete_node(state: QAState) -> dict:
    return {"current_task": None}
