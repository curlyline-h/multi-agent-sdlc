import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)
    path = Column(String(500), nullable=True)
    git_url = Column(String(500), nullable=True)
    current_status = Column(String(100), default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workflows = relationship("Workflow", back_populates="project", cascade="all, delete-orphan")
    command_executions = relationship("CommandExecution", back_populates="project", cascade="all, delete-orphan")
    file_records = relationship("FileRecord", back_populates="project", cascade="all, delete-orphan")


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    current_state = Column(String(100), default="START")
    current_subgraph_node = Column(String(100), nullable=True)
    completed_nodes = Column(Text, nullable=True, default="[]")  # JSON list of completed parent node names
    status = Column(String(100), default="RUNNING")
    source_branch = Column(String(255), nullable=True)
    target_branch = Column(String(255), nullable=True)
    next_agent = Column(String(100), nullable=True)
    summary = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="workflows")
    tasks = relationship("Task", back_populates="workflow", cascade="all, delete-orphan")
    logs = relationship("AgentLogModel", back_populates="workflow", cascade="all, delete-orphan")
    approvals = relationship("HumanApproval", back_populates="workflow", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True)
    requesting_agent_id = Column(String(255), nullable=True)
    status = Column(String(100), default="PENDING")
    request_details = Column(Text, nullable=True)
    payload = Column(Text, nullable=True)
    response = Column(String(4000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="tasks")


class AgentLogModel(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True)
    requesting_agent_id = Column(String(255), nullable=True)
    status = Column(String(100), default="INFO")
    request_details = Column(Text, nullable=True)
    payload = Column(Text, nullable=True)
    response = Column(String(4000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="logs")


class HumanApproval(Base):
    __tablename__ = "human_approval"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True)
    requesting_agent_id = Column(String(255), nullable=True)
    status = Column(String(100), default="PENDING")
    request_details = Column(Text, nullable=True)
    payload = Column(Text, nullable=True)
    feed_back = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="approvals")


class CommandExecution(Base):
    __tablename__ = "command_executions"

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    agent_role = Column(String(100), nullable=False)
    command = Column(Text, nullable=False)
    cwd = Column(String(500), nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    exit_code = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="command_executions")


class FileRecord(Base):
    __tablename__ = "file_records"

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(500), nullable=False)
    action = Column(String(50), nullable=False)
    diff_snapshot = Column(Text, nullable=True)
    content_snapshot = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="file_records")
