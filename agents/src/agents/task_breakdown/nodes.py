"""
Task Breakdown Agent — Node Functions

Flow:
  generate_tasks
"""
import json
from typing import List
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from agents.src.shared.llm import get_llm

from agents.src.agents.task_breakdown.state import TaskBreakdownState

_llm = get_llm(temperature=0.1, max_tokens=2500)

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
    from langchain_core.messages import SystemMessage, HumanMessage
    import os
    
    # Load system prompt from file
    prompt_path = os.path.join(os.path.dirname(__file__), "../../prompts/task_breakdown.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()
    
    system_prompt += "\n\nCRITICAL: Generate exactly 7 to 10 atomic tasks covering the SDLC sequence (database_engineer -> backend -> frontend -> qa -> reviewer -> security -> devops). Keep descriptions under 12 words. Respond ONLY with valid raw JSON: {\"tasks\": [{\"title\": \"...\", \"description\": \"...\", \"assignee_role\": \"...\", \"priority\": 1, \"dependencies\": [...]}]}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Here is the PRD:\n{(state.prd or '')[:3500]}\n\nHere is the Design Document:\n{(state.final_design_doc or '')[:4500]}\n\nGenerate the tasks JSON now.")
    ]
    
    try:
        from agents.src.shared.llm import llm_invoke_with_retry
        response = llm_invoke_with_retry(_llm, messages)
        
        # Extract JSON using regex in case there's markdown
        import re, json
        content = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
        # Strip markdown fences if present
        if "```" in content:
            fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if fence_match:
                content = fence_match.group(1).strip()
            else:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0).strip()
        else:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0).strip()
            
        try:
            parsed = json.loads(content)
            raw_tasks = parsed.get("tasks", [])
        except Exception:
            try:
                cleaned = re.sub(r',\s*([}\]])', r'\1', content)
                parsed = json.loads(cleaned)
                raw_tasks = parsed.get("tasks", [])
            except Exception:
                # Salvage individual task objects from partially truncated JSON
                raw_tasks = []
                for m in re.finditer(r'\{[^{}]*"title"\s*:\s*"[^"]+"[^{}]*\}', content, re.DOTALL):
                    try:
                        raw_tasks.append(json.loads(re.sub(r',\s*([}\]])', r'\1', m.group(0))))
                    except Exception:
                        pass
        tasks = []
        for t in raw_tasks:
            if isinstance(t, dict) and t.get("title") and t.get("title") != "Parse Error":
                role = t.get("assignee_role") or t.get("assignee") or t.get("role") or "backend"
                t["assignee_role"] = role
                tasks.append(t)
    except Exception as e:
        print(f"[TaskBreakdown] Warning: LLM task breakdown parse failed ({e}); synthesizing structured SDLC DAG.")
        tasks = []

    if len(tasks) < 5:
        tasks = [
            {"title": "Create DB Schema", "description": "Design and migrate core relational tables, indexes, and constraints.", "assignee_role": "database_engineer", "priority": 1, "dependencies": []},
            {"title": "Build Core Backend Services", "description": "Implement domain services, business logic, and data access layer.", "assignee_role": "backend", "priority": 2, "dependencies": ["Create DB Schema"]},
            {"title": "Build REST API Endpoints", "description": "Implement HTTP routes, request validation, and authentication middleware.", "assignee_role": "backend", "priority": 3, "dependencies": ["Build Core Backend Services"]},
            {"title": "Build Frontend Dashboard UI", "description": "Implement responsive web interface and API client integration.", "assignee_role": "frontend", "priority": 4, "dependencies": ["Build REST API Endpoints"]},
            {"title": "Write E2E & Integration Tests", "description": "Create automated unit, integration, and end-to-end test suites.", "assignee_role": "qa", "priority": 5, "dependencies": ["Build REST API Endpoints", "Build Frontend Dashboard UI"]},
            {"title": "Perform Code & Architecture Review", "description": "Audit implementation against PRD requirements and architecture standards.", "assignee_role": "reviewer", "priority": 6, "dependencies": ["Write E2E & Integration Tests"]},
            {"title": "Execute SAST & Security Audit", "description": "Run static security analysis, dependency checks, and auth verification.", "assignee_role": "security", "priority": 7, "dependencies": ["Perform Code & Architecture Review"]},
            {"title": "Configure Docker & CI/CD Pipeline", "description": "Create Dockerfile, docker-compose, and GitHub Actions deployment workflow.", "assignee_role": "devops", "priority": 8, "dependencies": ["Execute SAST & Security Audit"]},
        ]

    return {"workflow_tasks": tasks}
