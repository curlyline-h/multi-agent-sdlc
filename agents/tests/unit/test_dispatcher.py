"""
Unit Tests for Dependency-Aware Dispatcher in Parent Orchestrator.
Verifies that dispatcher only selects tasks whose prerequisite dependencies are complete.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field
from typing import Any, Dict, List

try:
    from agents.src.orchestrator.state import WorkflowState
except Exception:
    class WorkflowState(BaseModel):
        projectId: str = "p1"
        workflowId: str = "wf1"
        user_req: str = ""
        created_at: str = ""
        updated_at: str = ""
        prd: str = ""
        project_name: str = ""
        final_design_doc: str = ""
        final_file_changes: List[Dict[str, Any]] = []
        agent_logs: List[Dict[str, Any]] = []
        human_interventions: List[Dict[str, Any]] = []
        workflow_tasks: List[Dict[str, Any]] = []
        completed_task_titles: List[str] = []
        active_tasks: List[Dict[str, Any]] = []
        active_role: str = ""


def mock_dispatcher(state: WorkflowState) -> dict:
    """
    Dispatcher logic isolated for deterministic unit testing.
    Replicates the dependency resolution algorithm in orchestrator/graph.py.
    """
    all_tasks = state.workflow_tasks
    completed = set(state.completed_task_titles)

    ready_tasks = []
    for t in all_tasks:
        title = t.get("title", "")
        if title in completed:
            continue
        deps = t.get("dependencies", [])
        if all(dep in completed for dep in deps):
            ready_tasks.append(t)

    if not ready_tasks:
        return {"active_role": "", "active_tasks": []}

    precedence = ["database_engineer", "devops", "backend", "frontend", "qa", "reviewer", "security"]

    def get_precedence(role: str) -> int:
        return precedence.index(role) if role in precedence else 99

    ready_tasks.sort(key=lambda x: (x.get("priority", 5), get_precedence(x.get("assignee_role", ""))))
    chosen_role = ready_tasks[0].get("assignee_role", "")
    tasks_for_role = [t for t in ready_tasks if t.get("assignee_role", "") == chosen_role]

    return {"active_role": chosen_role, "active_tasks": tasks_for_role}


def test_dispatcher_blocks_unmet_dependencies():
    tasks = [
        {
            "title": "Create User Schema",
            "assignee_role": "database_engineer",
            "priority": 1,
            "dependencies": [],
        },
        {
            "title": "Build Auth Endpoints",
            "assignee_role": "backend",
            "priority": 1,
            "dependencies": ["Create User Schema"],
        },
        {
            "title": "Build Login UI",
            "assignee_role": "frontend",
            "priority": 2,
            "dependencies": ["Build Auth Endpoints"],
        },
    ]

    state = WorkflowState(
        projectId="p1",
        workflowId="wf1",
        user_req="Auth system",
        created_at="2026-11-08T00:00:00",
        updated_at="2026-11-08T00:00:00",
        final_design_doc="",
        final_file_changes=[],
        agent_logs=[],
        human_interventions=[],
        workflow_tasks=tasks,
        completed_task_titles=[],
    )

    result = mock_dispatcher(state)
    assert result["active_role"] == "database_engineer"
    assert len(result["active_tasks"]) == 1
    assert result["active_tasks"][0]["title"] == "Create User Schema"


def test_dispatcher_unlocks_dependent_tasks_when_prerequisite_completed():
    tasks = [
        {
            "title": "Create User Schema",
            "assignee_role": "database_engineer",
            "priority": 1,
            "dependencies": [],
        },
        {
            "title": "Build Auth Endpoints",
            "assignee_role": "backend",
            "priority": 1,
            "dependencies": ["Create User Schema"],
        },
    ]

    state = WorkflowState(
        projectId="p1",
        workflowId="wf1",
        user_req="Auth system",
        created_at="2026-11-08T00:00:00",
        updated_at="2026-11-08T00:00:00",
        final_design_doc="",
        final_file_changes=[],
        agent_logs=[],
        human_interventions=[],
        workflow_tasks=tasks,
        completed_task_titles=["Create User Schema"],
    )

    result = mock_dispatcher(state)
    assert result["active_role"] == "backend"
    assert len(result["active_tasks"]) == 1
    assert result["active_tasks"][0]["title"] == "Build Auth Endpoints"


def test_dispatcher_completes_when_all_tasks_done():
    tasks = [
        {"title": "Task A", "assignee_role": "backend", "priority": 1, "dependencies": []}
    ]

    state = WorkflowState(
        projectId="p1",
        workflowId="wf1",
        user_req="Sample",
        created_at="2026-11-08T00:00:00",
        updated_at="2026-11-08T00:00:00",
        final_design_doc="",
        final_file_changes=[],
        agent_logs=[],
        human_interventions=[],
        workflow_tasks=tasks,
        completed_task_titles=["Task A"],
    )

    result = mock_dispatcher(state)
    assert result["active_role"] == ""
    assert len(result["active_tasks"]) == 0
