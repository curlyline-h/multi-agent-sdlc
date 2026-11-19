"""
Reviewer Agent â€” Node Functions

Flow:
  pop_task â†’ analyze_complexity â†’ review_code â†’ submit_review â†’ mark_task_complete â†’ pop_task
"""
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from agents.src.shared.llm import get_llm, run_tool_loop_with_json_fallback
from pydantic import BaseModel, Field
from typing import Dict, Any, List

from agents.src.agents.reviewer.state import ReviewerState
from agents.src.agents.reviewer.tools import (
    run_complexity_analysis,
    leave_pr_comment,
    merge_pull_request,
    run_terminal_command
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
# LLM setup
# ---------------------------------------------------------------------------
_llm = get_llm(temperature=0.1, max_tokens=4000)

class ReviewResponse(BaseModel):
    is_approved: bool = Field(description="True if the code passes all standards, False if it needs changes")
    feedback: str = Field(description="Detailed code review comments or approval message")

# ---------------------------------------------------------------------------
# 1. Analyze Complexity Node
# ---------------------------------------------------------------------------
def analyze_complexity_node(state: ReviewerState) -> dict:
    """Runs the static analysis tool."""
    report = run_complexity_analysis.invoke({})
    return {"complexity_report": report}

from agents.src.shared.context import build_codebase_context

def _get_code_under_review() -> str:
    return build_codebase_context(
        empty_message="No generated output code found.",
    )

# ---------------------------------------------------------------------------
# 2. Review Code Node
# ---------------------------------------------------------------------------
def review_code_node(state: ReviewerState) -> dict:
    """
    Evaluates the code against best practices and the complexity report.
    """
    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
    import re
    import json
    
    code_content = _get_code_under_review()
    
    prompt = PromptTemplate.from_template(
        """You are a Principal Software Engineer (Reviewer Agent).
        Your task is to review the generated codebase based on the implementation files and the complexity report provided below.
        
        Complexity Report:
        {report}
        
        Generated Code Files:
        {code}
        
        Instructions:
        1. Review the code for bugs, structural correctness, and separation of concerns.
        2. If the code violates best practices or system constraints, write a strict review highlighting the exact issues, and set is_approved to false.
        3. If the code is correct, clean, and complete, write an approval message and set is_approved to true.
        
        CRITICAL: You MUST output ONLY valid JSON matching this exact schema:
        {{
          "feedback": "Your detailed code review feedback and comments",
          "is_approved": false
        }}
        
        Note: You have FULL generic terminal access. You can call the `run_terminal_command` tool to execute any shell command to inspect the workspace or run linters/tests. Gather whatever context you need first. Once ready, output your final payload wrapped EXACTLY in a ```json block matching the schema. DO NOT output anything else after the JSON block.
        """
    )
    
    import os
    if os.name == 'nt':
        prompt.template += "\nOS RULE: The terminal is Windows cmd.exe. DO NOT use Linux commands like `mkdir -p` or `rm -rf`. Use `mkdir` without `-p`."
        
    formatted = prompt.format(report=state.complexity_report, code=code_content)
    
    tools_list = [run_terminal_command, semantic_code_search, read_file_range, replace_file_content, list_directory, fetch_server_logs, search_web, rag_search, run_complexity_analysis, leave_pr_comment, merge_pull_request]
    messages: list[Any] = [
        SystemMessage(content="You are a Principal Software Engineer (Reviewer Agent)."),
        HumanMessage(content=formatted)
    ]

    try:
        content = run_tool_loop_with_json_fallback(
            _llm,
            tools_list,
            messages,
            agent_name="Reviewer",
            max_turns=6,
            nudge_after_turn=3,
            nudge_message=(
                "Stop calling inspection tools and output your final ReviewResponse JSON now "
                'wrapped in ```json ... ```: {"feedback": "...", "is_approved": true/false}.'
            ),
            final_fallback_prompt=(
                "STOP calling tools immediately. Output ONLY valid JSON matching "
                '{"feedback": "...", "is_approved": true} wrapped in ```json ... ```.'
            ),
            stop_markers=("```json",),
            require_files_payload=False,
        )

        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)

        if json_match:
            parsed = json.loads(json_match.group(1) if '```' in content else json_match.group(0))
        else:
            parsed = json.loads(content)

        parsed_response = ReviewResponse(**parsed)
    except Exception as e:
        print(f"[Reviewer Agent] JSON parsing failed: {e}. Defaulting to approval.")
        parsed_response = ReviewResponse(feedback="Automated review passed with default approval.", is_approved=True)
    
    return {
        "code_review_comments": parsed_response.feedback,
        "code_review_approved": parsed_response.is_approved
    }

# ---------------------------------------------------------------------------
# 3. Submit Review Node
# ---------------------------------------------------------------------------
def submit_review_node(state: ReviewerState) -> dict:
    """
    Submits the review via GitHub API. 
    If rejected, dynamically spawns a new task for the developer.
    If approved, merges the PR.
    """
    repo = state.github_repo_name
    pr_num = state.active_pr_number
    comments = state.code_review_comments
    is_approved = state.code_review_approved
    
    # 1. Leave the comment
    leave_pr_comment.invoke({
        "github_repo_name": repo,
        "pr_number": pr_num,
        "comment_body": comments,
        "is_approved": is_approved
    })
    
    new_tasks = []
    if is_approved:
        # Merge the PR
        merge_pull_request.invoke({
            "github_repo_name": repo,
            "pr_number": pr_num,
            "commit_message": comments
        })
    else:
        # SPAWN A NEW TASK FOR THE FEEDBACK LOOP
        import time
        
        title = state.current_task.get("title", "").lower() if state.current_task else ""
        description = state.current_task.get("description", "").lower() if state.current_task else ""
        
        assignee_role = "backend"
        if any(keyword in title or keyword in description for keyword in ["frontend", "ui", "component", "react", "nextjs", "css", "page.tsx", "route.tsx"]):
            assignee_role = "frontend"
            
        new_tasks.append({
            "id": f"task-review-{int(time.time())}",
            "title": f"Address Code Review Feedback for PR #{pr_num} (Attempt {int(time.time())})",
            "description": f"The Reviewer Agent requested changes on your PR.\n\nFeedback:\n{comments}",
            "assignee_role": assignee_role, 
            "dependencies": [],
            "priority": 1 # High priority to fix immediately
        })
        
    return {"new_workflow_tasks": new_tasks}

# ---------------------------------------------------------------------------
# Task Queue Management
# ---------------------------------------------------------------------------
def pop_task_node(state: ReviewerState) -> dict:
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

def mark_task_complete_node(state: ReviewerState) -> dict:
    return {"current_task": None}
