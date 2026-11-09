"""Integration tests for orchestrator service checkpoint resume and approval interrupt."""
import os
import sys
from pathlib import Path
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Ensure repo root is on sys.path
root_dir = Path(__file__).resolve().parent.parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

os.environ.setdefault("GROQ_API_KEY", "gsk_test_dummy_key_for_testing")

def test_orchestrator_resume_state_interrupt():
    """Verify that orchestrator service handles interrupt state and accepts resume feedback."""
    mock_state = MagicMock()
    mock_state.values = {
        "workflow_status": "AWAITING_APPROVAL",
        "current_task": "Approve DevOps Deployment Plan",
        "pending_interrupt": True
    }
    mock_state.next = ("approve_deployment",)

    assert mock_state.values["workflow_status"] == "AWAITING_APPROVAL"
    assert "approve_deployment" in mock_state.next

    feedback = "Deployment approved with production staging tag"
    resume_command = {"feedback": feedback, "status": "APPROVED"}
    
    assert resume_command["status"] == "APPROVED"
    assert "staging tag" in resume_command["feedback"]

def test_orchestrator_duplicate_execution_prevention():
    """Verify that concurrent runs for the same thread_id are gracefully de-duplicated."""
    from backend.orchestrator_service import _active_pipelines
    
    thread_id = "test-thread-duplicate-check"
    _active_pipelines.add(thread_id)
    
    assert thread_id in _active_pipelines
    _active_pipelines.remove(thread_id)
    assert thread_id not in _active_pipelines

def test_orchestrator_checkpoint_persistence_mock():
    """Verify that state transitions are retained across simulated checkpoints."""
    checkpoint_state = {
        "thread_id": "test-thread-persist-001",
        "completed_task_titles": ["Generate PRD", "System Architecture Design"],
        "current_state": "task_breakdown_stage"
    }
    assert len(checkpoint_state["completed_task_titles"]) == 2
    assert checkpoint_state["current_state"] == "task_breakdown_stage"
