from langgraph.graph import StateGraph,START,END
from pydantic import BaseModel, Field
from shared.AgentTypes import AgentType
from shared.WorkflowState import WorkflowState
from typing import List,Dict,Any
from datetime import datetime

# THIS IS THE PARENT AND GLOBAL STATE
class WorkflowState(BaseModel):
    projectId:str=Field(description="Project ID")
    workflowId:str=Field(description="Workflow ID")
    user_req:str=Field(description="User requirement")
    created_at:datetime=Field(description="Created at")
    updated_at:datetime=Field(description="Updated at")
    prd:str=Field(default="", description="Product Requirements Document")
    project_name:str=Field(default="", description="Project Name slug")
    final_design_doc:str=Field(description="Design document")
    final_file_changes:List[Dict[str,Any]]=Field(description="List of file changes")
    agent_logs:List[Dict[str,Any]]=Field(description="List of agent logs")
    human_interventions:List[Dict[str,Any]]=Field(description="List of human interventions")
    workflow_tasks:List[Dict[str,Any]]=Field(description="List of all generated tasks")
    completed_task_titles: List[str] = Field(default_factory=list, description="Titles of tasks that are fully done")
    active_tasks: List[Dict[str,Any]] = Field(default_factory=list, description="Queue of tasks currently being processed by an agent")
    active_role: str = Field(default="", description="The agent role currently executing the active_tasks")
    active_pr_number: int = Field(default=0, description="The GitHub PR number currently under review")
    is_initial_build: bool = Field(default=True, description="True for parallel execution, False for targeted bug fixes")
    target_agent: str = Field(default="", description="If is_initial_build=False, which agent to target")
    qa_passed: bool = Field(default=False, description="Whether E2E tests passed")
    reviewer_approved: bool = Field(default=False, description="Whether static analysis passed")
    security_approved: bool = Field(default=False, description="Whether security scan passed")
    github_repo_name: str = Field(default="", description="The repository name for GitHub API calls")
