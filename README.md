# Multi-Agent SDLC Platform

[![Deliverable 1](https://img.shields.io/badge/Deliverable-D1_Passed-success)](https://github.com/curlyline-h/multi-agent-sdlc/releases/tag/d1)
[![Deliverable 2](https://img.shields.io/badge/Deliverable-D2_Passed-success)](https://github.com/curlyline-h/multi-agent-sdlc/releases/tag/d2)
[![Deliverable 3](https://img.shields.io/badge/Release-v1.0-blue)](https://github.com/curlyline-h/multi-agent-sdlc/releases/tag/v1.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An autonomous multi-agent software engineering framework orchestrating 11 specialized AI agents across the entire Software Development Lifecycle (SDLC) — from requirements elicitation and system architecture to coding, code review, security auditing, QA testing, and DevOps deployment.

---

## 🚀 Live Demo & Deployments

* **Frontend Dashboard (Next.js):** [https://multi-agent-sdlc.vercel.app](https://multi-agent-sdlc.vercel.app)
* **Backend API & Swagger Docs (FastAPI):** [https://multi-agent-sdlc-backend.onrender.com/docs](https://multi-agent-sdlc-backend.onrender.com/docs)
* **API Health Check:** `https://multi-agent-sdlc-backend.onrender.com/`

---

## 🏛️ System Architecture

The platform is designed around a directed cyclic state graph built with **LangGraph**:

```
[User Request]
       │
       ▼
 [Planning Agent] ──(Human Clarification Loop)
       │
       ▼
[Product Manager] ──(PRD Generation)
       │
       ▼
[System Architect] ──(Architecture & Schemas)
       │
       ▼
[Task Breakdown] ──(DAG Task Decomposition)
       │
       ▼
  [Dispatcher] ◄────────────────────────────────────────┐
   ├──► [Database Engineer] ──► [Security Agent] ───────┤
   ├──► [Backend Developer] ──► [Code Reviewer] ────────┤ (Feedback Loops)
   └──► [Frontend Developer] ──► [Code Reviewer] ───────┤
                                      │                 │
                                      ▼                 │
                                  [QA Agent] ───────────┘
                                      │
                                      ▼
                                [DevOps Agent]
                                      │
                                      ▼
                           [Deployment & Health]
```

### 🤖 The 11 Autonomous Agents
1. **Planning Agent:** Analyzes feasibility, asks clarifying questions, and triggers human approval gates.
2. **Product Manager Agent:** Authoring structured Product Requirements Documents (PRDs).
3. **Architect Agent:** Generates system architecture, database models, and API specs.
4. **Task Breakdown Agent:** Converts architectural specs into an actionable directed acyclic task graph.
5. **Dispatcher Hub:** Dependency-aware task scheduler dispatching ready sub-tasks.
6. **Backend Developer Agent:** Implements FastAPI / Express backend routes and business logic.
7. **Frontend Developer Agent:** Implements responsive Next.js / React user interfaces.
8. **Database Engineer Agent:** Generates SQLAlchemy / PostgreSQL migrations and queries.
9. **Code Reviewer Agent:** Static analysis, lint checks, and clean-code feedback loops.
10. **Security Agent:** Scans for OWASP Top-10 vulnerabilities and planted security flaws.
11. **DevOps Agent:** Formulates Dockerfiles, docker-compose manifests, and health checks.

---

## 📊 Benchmark & Evaluation Results

Evaluated on a 40-scenario stratified benchmark dataset across 5 architectural categories:

| Metric | Single-Agent Baseline | Multi-Agent SDLC (Ours) | Relative Improvement |
| :--- | :---: | :---: | :---: |
| **Precision** | 0.68 | **0.91** | +33.8% |
| **Recall** | 0.62 | **0.86** | +38.7% |
| **F1-Score** | 0.65 | **0.88** | **+35.4%** |
| **AUC-ROC** | 0.71 | **0.89** | **+25.3%** |

---

## 🛠️ Quickstart Guide

### 1. Prerequisites
* Python 3.10+
* Node.js 18+ & npm
* Free Groq API Key (`console.groq.com/keys`)

### 2. Local Setup
```bash
# Clone the repository
git clone https://github.com/curlyline-h/multi-agent-sdlc.git
cd multi-agent-sdlc

# Install Python dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Set GROQ_API_KEY in .env

# Run FastAPI Backend
uvicorn backend.main:app --port 8000 --reload

# In a second terminal, run Next.js Frontend
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to access the interactive Multi-Agent Dashboard.

### 3. Docker Compose Setup
```bash
docker-compose -f infra/docker/docker-compose.yml up --build
```

---

## 📌 Note on Pretrained Model Weights

Per Deliverable 2 & 3 grading specifications: **No proprietary model weights need to be downloaded or hosted locally.** The platform leverages high-throughput, open-weights foundation models (`llama-3.3-70b-versatile` and `openai/gpt-oss-120b`) accessed via the authenticated **Groq API Cloud**. This guarantees deterministic evaluation and fast inference without local GPU constraints.

---

## 👥 Contribution Breakdown

| Member | Deliverable 1 | Deliverable 2 | Deliverable 3 | Total Commits |
| :--- | :---: | :---: | :---: | :---: |
| **Hania Zahra** | 5 | 11 | 10 | **26** |
| **Hamza Abbas** | 4 | 12 | 9 | **25** |
| **Muhammad Abdullah** | 4 | 12 | 10 | **26** |
| **Total** | **13** | **35** | **29** | **77** |
