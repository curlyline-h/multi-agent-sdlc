# Multi-Agent SDLC Platform

[![Deliverable 1](https://img.shields.io/badge/Deliverable-D1_Report_PDF-success)](report/Deliverable_1_Report.pdf)
[![Deliverable 2](https://img.shields.io/badge/Deliverable-D2_Report_PDF-success)](report/Deliverable_2_Report.pdf)
[![Deliverable 3](https://img.shields.io/badge/Release-v1.0-blue)](https://github.com/curlyline-h/multi-agent-sdlc/releases/tag/v1.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An autonomous multi-agent software engineering framework orchestrating 11 specialized AI agents across the entire Software Development Lifecycle (SDLC) — from requirements elicitation and system architecture to coding, code review, security auditing, QA testing, and DevOps deployment.

---

## 📑 Deliverable Reports
* **Deliverable 1 Report (PDF):** [`report/Deliverable_1_Report.pdf`](report/Deliverable_1_Report.pdf)
* **Deliverable 2 Report (PDF):** [`report/Deliverable_2_Report.pdf`](report/Deliverable_2_Report.pdf)

---

## 🎯 Phase 1: Project Framing and Problem Definition

### 1. Problem Statement
Modern enterprise software engineering requires continuous coordination across disjoint disciplines: requirements gathering, architectural modeling, database schema design, frontend/backend implementation, automated testing, and security compliance. Despite rapid advances in foundation LLMs, existing developer tools remain predominantly point-solution code completion assistants. Monolithic single-agent LLMs suffer from severe failure modes when applied to end-to-end SDLC workflows:
1. **Context Window Saturation and Drift:** As multi-file specifications, schemas, and test cases accumulate, single-agent models suffer from attention diffusion, dropping critical non-functional constraints (e.g., database foreign-key indexing, CORS headers).
2. **Unchecked Hallucinations:** Monolithic models lack internal verification loops, routinely inventing non-existent library APIs or generating insecure code snippets.
3. **Lack of Specialized Role Persona:** A single prompt context cannot effectively adopt the adversarial mindset of a security auditor while simultaneously acting as a UX designer and database optimizer.

### 2. Target Audience
* **Agile Engineering Teams and Technical Leads:** Rapidly bootstrap verified full-stack prototypes, complete with OpenAPI contracts, relational schemas, and unit tests directly from Jira issue tickets.
* **Full-Stack Developers:** Offload repetitive scaffolding, boilerplate generation, and initial AST linting/security audits while preserving architectural consistency.
* **DevOps and Quality Assurance Engineers:** Automate the generation of deterministic test fixtures, static vulnerability scans, and production Docker deployment manifests.

### 3. AI Justification: Machine Learning vs. Rule-Based Approaches
Traditional software scaffolding solutions (Yeoman, cookiecutter, Rails generators) rely on rigid, deterministic code templates and static syntax trees. While these deterministic tools excel at generating uniform directory structures, they cannot interpret ambiguous business specifications, reason across business domains, or diagnose and recover from runtime compiler errors. Deep learning foundation models and multi-agent systems possess rich natural language comprehension, semantic program synthesis capabilities, and multi-turn conversational reasoning. By structuring these capabilities into a specialized, cooperative multi-agent graph with discrete feedback loops and human-in-the-loop validation gates, our framework balances autonomous creativity with strict engineering determinism.

---

## 🚀 Live Demo & Deployments

* **Frontend Dashboard (Next.js):** [https://multi-agent-sdlc.vercel.app](https://multi-agent-sdlc.vercel.app)
* **Backend API & Swagger Docs (FastAPI):** [https://multi-agent-sdlc-backend.onrender.com/docs](https://multi-agent-sdlc-backend.onrender.com/docs)
* **API Health Check:** `https://multi-agent-sdlc-backend.onrender.com/`

---

## 🏛️ System Architecture

The platform is designed around a directed cyclic state graph built with **LangGraph**:

```
[User Request / Jira Ticket]
       │
       ▼
 [Planning Agent] ──(Human Clarification Gate)
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
  [Dispatcher Hub] ◄────────────────────────────────────────┐
   ├──► [Database Engineer] ──► [Security Agent] ───────┤
   ├──► [Backend Developer] ──► [Code Reviewer] ────────┤ (Revision Feedback Loops: Max K=2)
   └──► [Frontend Developer] ──► [Code Reviewer] ───────┤
                                      │                 │
                                      ▼                 │
                                  [QA Agent] ───────────┘
                                      │
                                      ▼
                                [DevOps Agent]
                                      │
                                      ▼
                            [Deployment & Health Gate]
```

### 🤖 The 11 Autonomous Agents
1. **Planning Agent:** Analyzes feasibility, asks clarifying questions, and triggers human approval gates.
2. **Product Manager Agent:** Authors structured Product Requirements Documents (PRDs).
3. **Architect Agent:** Generates system architecture, database models, and API specs.
4. **Task Breakdown Agent:** Converts architectural specs into an actionable directed acyclic task graph.
5. **Dispatcher Hub:** Dependency-aware task scheduler dispatching ready sub-tasks.
6. **Backend Developer Agent:** Implements FastAPI backend routes and business logic.
7. **Frontend Developer Agent:** Implements responsive Next.js / React user interfaces.
8. **Database Engineer Agent:** Generates SQLAlchemy / PostgreSQL migrations and queries.
9. **Code Reviewer Agent:** Static analysis, AST lint checks, and clean-code feedback loops.
10. **Security Agent:** Scans for OWASP Top-10 vulnerabilities, CWEs, and calculates risk scores.
11. **DevOps Agent:** Formulates Dockerfiles, docker-compose manifests, and health checks.

---

## 📊 Benchmark & Evaluation Results

Evaluated on a 40-scenario stratified benchmark dataset across 5 architectural categories (CRUD, REST APIs, Authentication, Database Apps, and E-commerce):

| Metric | Single-Agent Baseline | Multi-Agent SDLC (Ours) | Relative Improvement |
| :--- | :---: | :---: | :---: |
| **Precision** | 0.68 | **0.91** | **+33.8%** |
| **Recall** | 0.62 | **0.86** | **+38.7%** |
| **F1-Score** | 0.65 | **0.88** | **+35.4%** |
| **AUC-ROC** | 0.71 | **0.89** | **+25.4%** |

### Key Empirical Findings:
* **Self-Correction Success:** The closed-loop Reviewer and QA subgraphs intercept and self-correct **82.0%** of syntax, hallucinated import, and requirement omission errors prior to human presentation.
* **Fairness & Low Bias:** Variance across the five software categories is constrained to $\Delta F_1 = 0.07$ (ranging from 0.85 to 0.92, $\sigma = 0.025$).
* **Closed-Loop Error Convergence:** In single-agent runs, error drifts from 0.42 to 0.61 across lifecycle stages; multi-agent closed-loop execution drives error down from 0.38 to 0.05.

---

## 🔗 Pretrained Model Weights (>100MB Policy)

In accordance with Deliverable 2 submission guidelines, large pretrained model weights (>100MB) are hosted externally on the official Hugging Face Hub:
* **Foundation LLM Backbone:** [`meta-llama/Llama-3.3-70B-Instruct`](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct) — High-throughput open-weights LLM running via Groq Cloud API for ultra-fast multi-turn reasoning ($>250$ tokens/sec).
* **Dense Embedding Model:** [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) — 384-dimensional dense semantic sentence embeddings used in the Hybrid ChromaDB + BM25 RAG retriever.

---

## 🛠️ Quickstart Guide

### 1. Prerequisites
* Python 3.10+
* Node.js 18+ & npm
* PostgreSQL 16 with `pgvector` extension
* Free Groq API Key (`console.groq.com/keys`)
* Atlassian Jira Account (optional for Jira sync)

### 2. Local Setup
```bash
# Clone the repository
git clone https://github.com/curlyline-h/multi-agent-sdlc.git
cd multi-agent-sdlc

# Install Python dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Set GROQ_API_KEY, DATABASE_URL, JIRA credentials in .env

# Run FastAPI Backend (port 8001 or 8000)
uvicorn backend.main:app --port 8001 --reload

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

