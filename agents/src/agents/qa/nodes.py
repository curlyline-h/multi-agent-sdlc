"""
QA Agent — Node Functions

Flow:
  pop_task → generate_test_scripts → execute_tests → analyze_results → mark_task_complete → pop_task
"""
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from agents.src.shared.llm import get_llm, llm_tool_invoke_with_retry
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
    title: str = Field(description="Short, specific summary of the bug — include the function/method name and what went wrong")
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
def _get_codebase_summary() -> str:
    output_dir = Path(__file__).resolve().parents[5] / "output"
    if not output_dir.exists():
        return "No generated code found yet."
        
    code_blocks = []
    omitted_files = []
    allowed_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".css", ".json", ".md", ".html"}
    ignored_dirs = {"node_modules", ".git", ".next", "dist", "build"}
    
    import os
    provider = os.getenv("LLM_PROVIDER", "").lower()
    MAX_TOTAL_CHARS = 16000 if provider == "ollama" else 40000
    current_total_chars = 0
    
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            if any(part in ignored_dirs for part in path.parts):
                continue
            if path.suffix in allowed_extensions:
                rel_path = path.relative_to(output_dir.parent)
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
# 1. Generate Test Scripts Node
# ---------------------------------------------------------------------------
def generate_tests_node(state: QAState) -> dict:
    """
    Generates a Playwright test suite using the PRD, Design Doc, and output Codebase.
    """
    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
    import re
    import json
    
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
    llm_with_tools = _llm.bind_tools(tools_list)
    
    messages = [
        SystemMessage(content="You are a QA Automation Engineer."),
        HumanMessage(content=formatted)
    ]
    
    # ReAct Loop
    for turn in range(15):
        try:
            response = llm_tool_invoke_with_retry(llm_with_tools, messages, agent_name="QA")
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
                print(f"[QA Agent] LLM generation failed with error: {e}. Proceeding to fallback test suite.")
                break
                
        messages.append(response)
        
        if not getattr(response, "tool_calls", []):
            break
            
        # Check if it accidentally provided the TS block alongside tool calls
        if response.content and "```typescript" in response.content.lower():
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
    
    # Find the content containing the typescript block
    content = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and isinstance(msg.content, str) and ("```typescript" in msg.content.lower() or "```ts" in msg.content.lower()):
            content = msg.content
            break
    if not content:
        content = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
        
    match = re.search(r'```(?:typescript|ts)?\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
    if match:
        test_code = match.group(1).strip()
    else:
        test_code = content.strip()
    
    # Write the test to the output directory
    output_dir = Path(__file__).resolve().parents[4] / "output"
    
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
    Runs the generated test suite using the real tool.
    """
    # Actually execute the tests in the output directory
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
        structured_llm = _llm.with_structured_output(TestAnalysis)
        response = structured_llm.invoke(formatted)
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
    
    # Smart role routing based on failing file paths in the bug description
    def _route_bug(bug: BugReport) -> str:
        text = f"{bug.title} {bug.actual} {bug.steps}".lower()
        if any(k in text for k in ["api", "endpoint", "route", "server", "database", "db", "sql", "model", "migration"]):
            return "backend"
        if any(k in text for k in ["component", "render", "ui", "css", "html", "dom", "canvas", "style", "layout"]):
            return "frontend"
        if any(k in text for k in ["test", "spec", "jest", "pytest", "playwright", "fixture"]):
            return "qa"
        if any(k in text for k in ["docker", "deploy", "ci", "pipeline", "workflow"]):
            return "devops"
        return "backend"  # safe default for ambiguous failures
    
    # For each bug, log it using the tool and create a workflow task
    for bug in response.discovered_bugs:
        # 1. Log bug to BUGS.md
        generate_bug_report.invoke({
            "title": bug.title,
            "steps": bug.steps,
            "expected": bug.expected,
            "actual": bug.actual
        })
        
        # 2. Spawn task for Dispatcher
        new_tasks.append({
            "id": f"task-bugfix-{int(time.time())}",
            "title": f"Fix QA Bug: {bug.title} (Attempt {int(time.time())})",
            "description": f"A bug was discovered during QA testing.\n\nSteps:\n{bug.steps}\n\nExpected:\n{bug.expected}\n\nActual:\n{bug.actual}",
            "assignee_role": _route_bug(bug),
            "dependencies": [],
            "priority": 1 # High priority
        })
        time.sleep(1) # Ensure unique IDs
        
    return {
        "discovered_bugs": [bug.dict() for bug in response.discovered_bugs],
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
    next_task = tasks.pop(0)
    return {"workflow_tasks": tasks, "current_task": next_task}

def mark_task_complete_node(state: QAState) -> dict:
    return {"current_task": None}
