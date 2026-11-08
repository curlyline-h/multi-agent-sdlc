# Multi-Agent SDLC Orchestrator

## Overview
**Multi-Agent SDLC Orchestrator** is an autonomous, stateful software engineering platform powered by a coordinated graph of 11 specialized Large Language Model (LLM) agents built on LangGraph, FastAPI, and Next.js. Given a natural-language software requirement, the system performs end-to-end Software Development Life Cycle (SDLC) execution: feasibility analysis, Product Requirements Document (PRD) drafting, system architecture design, dependency-aware task breakdown, database schema engineering, backend and frontend implementation, automated code review, static security scanning, QA test generation, and DevOps containerization.

## Problem Statement
Modern software delivery teams spend significant engineering cycles translating high-level product requirements into consistent architectural designs, granular sprint tasks, boilerplate implementations, and verification suites. Existing single-prompt LLM code assistants suffer from three critical limitations on full-stack projects:
1. **Context Window Saturation & Hallucination:** A single LLM prompted to generate an entire multi-tier application simultaneously loses track of cross-file interfaces, database schemas, and API contracts.
2. **Lack of Dependency Ordering:** Without explicit DAG-based task scheduling, code is generated out of dependency order (e.g., frontend views referencing non-existent backend endpoints or unmigrated tables).
3. **Absence of Closed-Loop Quality Gates:** Single-pass generation lacks adversarial verification for security vulnerabilities (OWASP Top 10), static code quality, and automated end-to-end test execution before deployment.

## Target Users
- **Software Engineering Teams & Startups:** Rapidly scaffolding production-grade full-stack applications (PostgreSQL/SQLite, FastAPI, Next.js, Docker) with traceable PRDs, Jira tickets, and GitHub Pull Requests.
- **Technical Product Managers & System Architects:** Validating requirement feasibility, generating architectural specifications, and decomposing features into dependency-ordered engineering tasks with human-in-the-loop approval gates.
- **AI & Software Engineering Researchers:** Benchmarking multi-agent orchestration against single-agent LLM baselines across requirement coverage, task DAG accuracy, and security vulnerability detection.

## Why Multi-Agent LLM Orchestration Beats Rule-Based & Single-LLM Generation
- ** vs. Rule-Based / Template Code Generators:** Rule-based scaffolds (e.g., Yeoman, OpenAPI generators) require rigid, formal schemas up front and cannot reason about ambiguous natural-language business logic, edge-case security constraints, or custom domain workflows.
- ** vs. Single-Agent Prompt Chains:** By decomposing the SDLC into specialized stateful subgraphs (`planning`, `product_manager`, `architect`, `task_breakdown`, `database_engineer`, `backend_dev`, `frontend_dev`, `reviewer`, `security`, `qa`, `devops`) coordinated by a dependency-aware dispatcher and iterative critique loops, each agent operates with focused domain prompts, scoped tools, and explicit verification feedback.

## Benchmark & Data Pipeline (`data_scripts/`)
Deliverable 1 provides a 40-scenario software engineering benchmark spanning five application categories (`crud`, `rest_api`, `ecommerce`, `auth`, `db_app`), combining 25 curated specification scenarios and 15 real-world feature requests adapted from GitHub Issues. See [`data_scripts/README.md`](data_scripts/README.md) for the full dataset pipeline and schema documentation.

