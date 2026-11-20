"""
Task Breakdown Agent — Node Functions

Flow:
  generate_tasks
"""
import json
from typing import List
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from agents.src.shared.llm import get_llm, llm_invoke_with_retry

from agents.src.agents.task_breakdown.state import TaskBreakdownState

_llm = get_llm(temperature=0.1, max_tokens=4000)

# ---------------------------------------------------------------------------
# 1. Generate Tasks Node
# ---------------------------------------------------------------------------
class Task(BaseModel):
    title: str = Field(description="The title of the task")
    description: str = Field(description="Detailed description of the task")
    assignee_role: str = Field(description="The role assigned: 'database_engineer', 'devops', 'backend', 'frontend', 'qa', 'reviewer', or 'security'")
    priority: int = Field(description="Priority from 1 (highest) to 10 (lowest). Tasks with no dependencies should have priority 1.")
    dependencies: List[str] = Field(description="List of task titles that this task depends on")

class TaskList(BaseModel):
    tasks: List[Task] = Field(description="A list of granular tasks for the project")

def generate_tasks_node(state: TaskBreakdownState) -> dict:
    """
    Reads the PRD and Architecture Doc, and breaks the project into granular JSON tasks.
    These tasks will be consumed by the Backend and Frontend Developer agents.
    """
    from langchain_core.prompts import ChatPromptTemplate
    import os
    
    # Load system prompt from file
    prompt_path = os.path.join(os.path.dirname(__file__), "../../prompts/task_breakdown.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt + "\n\nCRITICAL: Respond ONLY with a raw JSON object containing a 'tasks' array. Do not use markdown blocks like ```json. Do not include any other text."),
        ("user", "Here is the PRD:\n{prd}\n\nHere is the Design Document:\n{design}\n\nGenerate the tasks JSON now.")
    ])
    
    try:
        formatted = prompt.format_messages(
            prd=(state.prd or "")[:4000],
            design=(state.final_design_doc or "")[:6000]
        )
        
        response = llm_invoke_with_retry(_llm, formatted, label="TaskBreakdown")
        
        # Extract JSON using regex in case there's markdown
        import re, json
        content = response.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
            
        parsed = json.loads(content)
        raw_tasks = parsed.get("tasks", [])
        design_lower = (state.final_design_doc or "").lower()
        no_database = "database: none" in design_lower or "**database**: none" in design_lower

        tasks = []
        removed_titles: set[str] = set()
        for t in raw_tasks:
            if isinstance(t, dict):
                role = t.get("assignee_role") or t.get("assignee") or t.get("role") or "backend"
                if no_database and role == "database_engineer":
                    removed_titles.add(str(t.get("title", "")))
                    continue
                t["assignee_role"] = role
                tasks.append(t)

        # Clean up any dependencies referencing skipped no-DB tasks or unknown titles
        valid_titles = {str(t.get("title", "")) for t in tasks}
        for t in tasks:
            deps = t.get("dependencies") or []
            if isinstance(deps, list):
                t["dependencies"] = [
                    d for d in deps
                    if d in valid_titles and d != t.get("title") and d not in removed_titles
                ]
    except Exception as e:
        tasks = [{"title": "Parse Error", "description": f"Output failed: {e}", "assignee_role": "backend", "priority": 1, "dependencies": []}]
        
    return {"workflow_tasks": tasks}
