# 🤖 Multi-Agent SDLC — Autonomous Software Development Lifecycle System

> An AI-powered, fully autonomous Software Development Lifecycle (SDLC) system that takes a plain-English user requirement and orchestrates a team of specialized AI agents to plan, architect, build, review, test, secure, and deploy a working application — end-to-end, without human intervention.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Project Structure](#project-structure)
4. [The Agent Pipeline](#the-agent-pipeline)
5. [Orchestration Engine](#orchestration-engine)
6. [Backend API](#backend-api)
7. [Frontend Dashboard](#frontend-dashboard)
8. [Data Flow & State Management](#data-flow--state-management)
9. [Optimization Techniques](#optimization-techniques)
10. [Technology Stack](#technology-stack)
11. [Running the System](#running-the-system)
12. [Environment Variables](#environment-variables)

---

## Overview

**Multi-Agent SDLC** is a production-grade autonomous development platform. You give it a requirement like _"Build a Bubble Shooter game in React Native for Android"_ and it:

1. Conducts a **feasibility analysis** and produces a full PRD.
2. **Architecturally designs** the entire system with a technology stack.
3. **Breaks down** the PRD into granular, dependency-aware tasks.
4. **Dispatches** tasks to the correct specialized agent (Backend, Frontend, QA, etc.) in the correct order.
5. Has each agent **write code**, pass a linter, and push a **Pull Request to GitHub**.
6. Runs a **Reviewer** agent for static analysis, a **Security** agent for vulnerability scanning, and a **QA** agent for E2E tests.
7. Tracks everything in real-time via a **Next.js dashboard** with live logs, approval gates, and diffs.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend Dashboard                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Workflow     │  │  Live Logs   │  │  Git Diff    │              │
│  │  Visualizer  │  │  Streamer    │  │  Viewer      │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  WebSocket (WS) + REST API
┌──────────────────────────────▼──────────────────────────────────────┐
│                         FastAPI Backend                              │
│  ┌────────────────┐  ┌───────────────────┐  ┌──────────────────┐   │
│  │ Orchestrator   │  │  WebSocket        │  │  Telemetry       │   │
│  │ Service        │  │  Manager          │  │  Broadcaster     │   │
│  └───────┬────────┘  └───────────────────┘  └──────────────────┘   │
│          │  SQLite (Approvals, Projects, Logs)                       │
└──────────┼──────────────────────────────────────────────────────────┘
           │ Python API calls
┌──────────▼──────────────────────────────────────────────────────────┐
│                    LangGraph Orchestration Engine                     │
│                                                                       │
│   [planning] → [pm_phase_a] → [architect] → [task_breakdown]         │
│                                               │                       │
│                                    ┌──────────▼──────────────┐       │
│                                    │    Dispatcher Loop       │       │
│                                    │  (Dependency-Aware       │       │
│                                    │   Priority Scheduler)    │       │
│                                    └─┬────────────────────────┘       │
│              ┌──────────┬───────────┬┴────────┬──────────┬───────┐   │
│         [backend]  [frontend]  [database]  [devops]  [qa]  [reviewer]│
│                                                      [security]       │
└───────────────────────────────────────────────────────────────────────┘
                               │
                        Ollama / Groq / OpenAI LLM
```

---

## Project Structure

```
multi_agent_sdlc/
├── 📁 agents/                         # Core AI Agent Engine (Python)
│   ├── 📁 src/
│   │   ├── 📁 agents/                 # All specialized agent subgraphs
│   │   │   ├── 📁 planning/           # Feasibility analysis & PRD generation
│   │   │   ├── 📁 product_manager/    # PM Phase A (PRD) & Phase B (overview)
│   │   │   ├── 📁 architect/          # System design & technology selection
│   │   │   ├── 📁 task_breakdown/     # PRD → granular tasks with deps
│   │   │   ├── 📁 backend_dev/        # API & business logic code generation
│   │   │   ├── 📁 frontend_dev/       # UI component code generation
│   │   │   ├── 📁 database_engineer/  # Schema design & migration scripts
│   │   │   ├── 📁 qa/                 # E2E test generation & execution
│   │   │   ├── 📁 reviewer/           # Static code analysis & PR reviews
│   │   │   ├── 📁 security/           # Vulnerability scanning & CVE tickets
│   │   │   ├── 📁 devops/             # CI/CD, GitHub Actions, APK build
│   │   │   └── 📁 task_breakdown/     # High-level task allocation
│   │   ├── 📁 orchestrator/
│   │   │   ├── graph.py               # Main LangGraph workflow DAG
│   │   │   └── state.py               # Pydantic global WorkflowState schema
│   │   ├── 📁 llm/                    # LLM provider abstraction layer
│   │   ├── 📁 shared/                 # Shared GitHub, Git, utilities
│   │   ├── 📁 prompts/                # Centralized system prompt templates
│   │   ├── 📁 memory/                 # RAG memory and embedding modules
│   │   ├── 📁 mcp/                    # Model Context Protocol integrations
│   │   ├── 📁 rag/                    # Retrieval-Augmented Generation
│   │   ├── 📁 tools/                  # Cross-agent shared tool definitions
│   │   └── 📁 evaluation/             # Agent output quality evaluators
│   └── requirements.txt
│
├── 📁 backend/                         # FastAPI REST + WebSocket Server
│   ├── main.py                        # FastAPI app entry point, lifespan events
│   ├── orchestrator_service.py        # Pipeline run/resume lifecycle manager
│   ├── models.py                      # SQLAlchemy ORM models (Projects, Logs)
│   ├── schemas.py                     # Pydantic request/response schemas
│   ├── websocket_manager.py           # WebSocket connection pool manager
│   ├── telemetry.py                   # Real-time log & event broadcaster
│   ├── git_service.py                 # Git diff, file tree utilities
│   ├── database.py                    # Async SQLite session factory
│   └── 📁 routers/                    # Modular route handlers (projects, files…)
│
├── 📁 frontend/                        # Next.js 14 Dashboard (App Router)
│   └── 📁 src/
│       ├── 📁 app/                    # App Router page/layout files
│       ├── 📁 components/             # Reusable UI components
│       └── 📁 lib/                    # API clients, WebSocket hooks
│
├── 📁 output/                          # Generated code output directory
│   └── 📁 src/                        # All agent-produced source files land here
│
├── 📁 docs/                            # System documentation
├── 📁 scripts/                         # Helper launch scripts
├── 📁 infra/                           # Infrastructure/deployment configs
├── .env                                # Environment variables (model, API keys)
├── final_prd.md                        # The generated PRD for the current project
├── final_plan.md                       # The feasibility & design document
├── tasks-proj.json                     # All generated granular tasks (JSON)
└── checkpoints.sqlite                  # LangGraph state checkpoints (resume capability)
```

---

## The Agent Pipeline

The system runs a **linear bootstrap phase** followed by a **dynamic dispatch loop**.

### Phase 1: Bootstrap (Sequential)

| Stage | Agent | Responsibility |
| :--- | :--- | :--- |
| **1. Planning** | `planning` | Conducts feasibility analysis. Detects project type, complexity, risks, and constraints. Outputs `final_plan.md`. |
| **2. PM Phase A** | `product_manager` | Drafts a full Product Requirements Document (PRD). Defines features, edge cases, and acceptance criteria. Outputs `final_prd.md`. |
| **3. Architecture** | `architect` | Selects technology stack and designs the system layout (DB schema, API contracts, folder structure). |
| **4. Task Breakdown** | `task_breakdown` | Decomposes the PRD + Architecture into granular, assignable tasks. Each task has `title`, `assignee_role`, `priority`, and a `dependencies[]` list. |
| **5. PM Phase B** | `product_manager` | Writes a final project overview summary document for downstream agents. |

### Phase 2: The Dispatcher Loop (Dynamic)

After all bootstrap stages complete, the **Dispatcher** takes over and runs in a loop:

1. Scans all tasks from `tasks-proj.json`.
2. Evaluates which tasks have all their `dependencies[]` satisfied.
3. Applies a **priority + precedence sort** to select the highest-impact next agent role.
4. Batches all ready tasks for that single role and fires the agent subgraph.
5. Upon completion, the agent marks tasks as done, and the loop repeats.

The loop terminates only when all tasks are `completed` or the safety limit of **50 iterations** is exceeded.

---

## Orchestration Engine

The orchestration layer is built on **[LangGraph](https://langchain-ai.github.io/langgraph/)** — a graph-based state machine for multi-agent AI workflows.

### Key Design Decisions

#### 1. Persistent Checkpointing
Every node transition is atomically saved to **`checkpoints.sqlite`** via `AsyncSqliteSaver`. This means:
- If the server restarts or crashes mid-task, the pipeline **resumes from the exact point** where it stopped.
- Each agent subgraph runs in its own **isolated thread ID** (`{workflowId}-{agentRole}`), preventing cross-contamination of state.

#### 2. Interrupt Bubbling
When a subgraph hits a `human_approval` node (like the DevOps deployment approval gate), it raises a `GraphInterrupt`. The parent orchestrator's `_run_subgraph_with_interrupts` function **catches and re-raises** this interrupt up to the FastAPI layer, which broadcasts it to the frontend as a pending approval request. When the user clicks "Approve" in the dashboard, the `resume` API endpoint feeds the decision back down the chain.

#### 3. The Dispatcher's Safety Guards
- **Max iteration guard**: Terminates after 50 dispatcher cycles to prevent infinite loops.
- **Identical re-dispatch guard**: Detects if the same role with the same task set is being dispatched twice in a row (e.g., due to a stale state) and terminates.

---

## Backend API

The FastAPI server exposes REST endpoints and a persistent WebSocket stream.

### Key Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/projects` | Create and start a new SDLC pipeline run |
| `GET` | `/projects/{id}` | Fetch project status and metadata |
| `POST` | `/projects/{id}/resume` | Resume a pipeline paused at an interrupt |
| `GET` | `/workflows/project/{id}` | Fetch the full agent workflow graph for visualization |
| `GET` | `/logs/project/{id}` | Fetch all real-time agent log entries |
| `GET` | `/approvals/project/{id}` | Fetch pending human approval requests |
| `POST` | `/approvals/{id}/respond` | Submit an approval/rejection response |
| `GET` | `/files/tree` | Fetch the current output directory file tree |
| `GET` | `/files/git-diff` | Fetch the live git diff of all generated code |
| `WS` | `/ws/projects/{id}` | Real-time WebSocket stream for live log events |

---

## Frontend Dashboard

The **Next.js 14** dashboard (App Router) provides:
- **Workflow Visualizer**: A live, animated graph showing which agent is actively running and which stages have completed.
- **Live Terminal Log**: Streams all agent logs in real-time via WebSocket, showing sub-task completions, tool calls, and errors.
- **Code Diff Viewer**: Git-diff formatted view of all files generated so far.
- **File Tree**: Browsable output directory listing.
- **Approval Gates**: Modal dialogs for human-in-the-loop review of agent-generated deployment plans.
- **Document Viewer**: Renders the generated PRD, Architecture doc, and final plan.

---

## Data Flow & State Management

```
User Input (Natural Language Requirement)
    │
    ▼
WorkflowState (Pydantic Model — immutable, passed through graph nodes)
    │
    ├── prd              (generated PRD string)
    ├── final_design_doc (architecture document)
    ├── workflow_tasks   (List of all task dicts)
    ├── completed_task_titles (Set of finished task names)
    ├── active_tasks     (Queue for current agent)
    ├── active_role      (Current executing agent role)
    └── ...approval flags, scores, GitHub metadata

SQLite (checkpoints.sqlite)
    └── Stores every StateGraph checkpoint per thread_id
        └── Enables crash recovery & mid-pipeline resume

SQLite (database.sqlite)
    └── Projects, AgentLogs, ApprovalRequests (SQLAlchemy ORM models)
```

---

## Optimization Techniques

### 1. Decoupled Subgraph Threading
Each agent runs in its **own isolated LangGraph thread ID**, backed by its own SQLite checkpoint sequence. This prevents any one agent's state from polluting another and allows them to independently resume without re-running upstream stages.

### 2. Streaming Architecture (No Polling)
The system uses a persistent **WebSocket connection** instead of polling REST endpoints. The `telemetry.py` module maintains an in-memory log store and pushes live events to the frontend the instant they are emitted by any agent node.

### 3. Interrupt Replay Guard
LangGraph replays interrupted nodes when resuming. The `_subgraph_counters` dictionary tracks how many times an interrupt has been "seen" for a given thread. This prevents the system from incorrectly streaming completed events a second time when resuming, which would corrupt the checkpoint order.

### 4. Dependency-Aware Parallel-Ready Dispatch
The Dispatcher does not simply execute tasks serially. It evaluates all pending tasks and identifies the maximal set that is "ready" (all dependencies satisfied) for the **highest-priority role**. This means multiple tasks assigned to the same agent role execute in a single batch, dramatically reducing total pipeline time.

### 5. Pydantic Schema Enforcement
All inter-agent data (task lists, code files, PRD content) is serialized and validated through **Pydantic** schemas. This ensures that if an LLM produces malformed JSON, the pipeline catches the validation error, logs it gracefully, and uses a sensible default (e.g., `Defaulting to approval`) rather than crashing.

### 6. LLM Abstraction Layer (`agents/src/llm/`)
The LLM provider is fully swappable via the `.env` file. You can switch between Ollama (local), Groq (cloud API), or OpenAI with a single `LLM_MODEL` variable change. The abstraction layer handles context-window sizing, retry logic, and streaming.

### 7. Cumulative Git Commit Strategy
Rather than creating fragile incremental patches, each DevOps agent push does a **clean `git reset FETCH_HEAD`** before committing. This creates a cumulative snapshot PR — each PR represents the entire codebase up to that point, making code review much simpler and preventing rebase conflicts between sequential agent runs.

---

## Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Orchestration** | [LangGraph](https://langchain-ai.github.io/langgraph/) (Python) |
| **LLM Providers** | Ollama (Local), Groq, OpenAI — configurable |
| **Backend API** | FastAPI + Uvicorn (async Python) |
| **Database** | SQLite (dual: app data + LangGraph checkpoints) |
| **Frontend** | Next.js 14 (App Router, TypeScript) |
| **Real-Time** | WebSockets (native FastAPI + starlette) |
| **State Validation** | Pydantic v2 |
| **GitHub Integration** | PyGithub + git CLI (via subprocess) |
| **Code Quality** | Pre-commit hooks (Ruff, Black) |

---

## Running the System

### Prerequisites
- Python 3.11+
- Node.js 18+
- Ollama (for local LLMs) OR a Groq/OpenAI API key

### 1. Start Ollama (if using local models)
```bash
# Start Ollama pointing to your model storage drive
scripts\run_ollama_d.bat serve
```

### 2. Start the FastAPI Backend
```bash
# From the project root
uvicorn backend.main:app --reload --port 8000
```

### 3. Start the Next.js Frontend
```bash
cd frontend
npm run dev
```

### 4. Open the Dashboard
Navigate to [http://localhost:3000](http://localhost:3000), create a new project, enter your requirement, and watch the agents work!

---

## Environment Variables

Configure the system by editing the root `.env` file:

```env
# LLM Configuration
LLM_MODEL=llama3.2           # Any Ollama model, or Groq model name
GROQ_API_KEY=                # Your Groq API key (optional)
OPENAI_API_KEY=              # Your OpenAI API key (optional)

# GitHub Integration
GITHUB_TOKEN=                # GitHub Personal Access Token (for PR creation)
GITHUB_USERNAME=             # Your GitHub username

# Optional
OLLAMA_BASE_URL=http://localhost:11434
```

---

## Architecture Summary

The key insight behind this system is treating **LangGraph as a reliable state machine** rather than just a conversation loop. Each agent is a fully isolated, checkpointed subgraph that can be paused, inspected, resumed, or re-run without affecting any other agent. The Dispatcher acts as a priority-aware scheduler, and the FastAPI backend acts as the control plane — exposing the entire system's state to humans through a rich real-time dashboard with approval gates.

This architecture allows the system to handle **long-running autonomous tasks** (minutes to hours) reliably, without losing progress even if the server is restarted mid-execution.
