# SDLC Orchestrator Architecture Overview

This document presents the complete graph architecture of the SDLC Orchestrator, highlighting both the parent orchestrator loop and the individual subgraphs that execute within each stage.

---

## 1. Parent Orchestrator Graph

The parent orchestrator guides the project execution linearly through setup phases (Requirements Definition, PRD Creation, System Architecture Design, and Task Breakdown) before entering the **Dispatcher Loop** to orchestrate agent tasks.

```mermaid
graph TD
    %% Define Styles
    classDef parent fill:#1a1b26,stroke:#7aa2f7,stroke-width:2px,color:#fff;
    classDef startEnd fill:#f7768e,stroke:#333,stroke-width:1px,color:#fff;
    classDef loopNode fill:#2ac3de,stroke:#333,stroke-width:1px,color:#333;

    %% Nodes
    START[START]:::startEnd
    planning[Planning Stage]:::parent
    pm_a[PM Phase A Stage]:::parent
    architect[Architect Stage]:::parent
    breakdown[Task Breakdown Stage]:::parent
    pm_b[PM Phase B Stage]:::parent
    
    dispatcher{Dispatcher Stage}:::loopNode
    db_eng[Database Engineer Stage]:::parent
    devops[DevOps Stage]:::parent
    backend[Backend Dev Stage]:::parent
    frontend[Frontend Dev Stage]:::parent
    qa[QA Stage]:::parent
    reviewer[Reviewer Stage]:::parent
    security[Security Stage]:::parent
    
    END[END]:::startEnd

    %% Linear Setup
    START --> planning
    planning --> pm_a
    pm_a --> architect
    architect --> breakdown
    breakdown --> pm_b
    pm_b --> dispatcher

    %% Dispatcher Routing Loop
    dispatcher -- "Assign: database_engineer" --> db_eng
    dispatcher -- "Assign: devops" --> devops
    dispatcher -- "Assign: backend" --> backend
    dispatcher -- "Assign: frontend" --> frontend
    dispatcher -- "Assign: qa" --> qa
    dispatcher -- "Assign: reviewer" --> reviewer
    dispatcher -- "Assign: security" --> security
    dispatcher -- "No active tasks left" --> END

    %% Loop Backs
    db_eng --> dispatcher
    devops --> dispatcher
    backend --> dispatcher
    frontend --> dispatcher
    qa --> dispatcher
    reviewer --> dispatcher
    security --> dispatcher
```

---

## 2. Subgraph Workflows

Each wrapper stage in the parent orchestrator executes an isolated LangGraph subgraph using context-specific states and custom checkpointers. Below is the detailed breakdown of the subgraphs.

### A. Planning Subgraph
Processes the initial user requirements, clarifies ambiguities, and produces a structured feasibility plan.

```mermaid
graph TD
    classDef node fill:#1f2335,stroke:#9ece6a,stroke-width:1.5px,color:#fff;
    
    START((START)) --> clarification[Clarification Node]:::node
    clarification --> generate_draft[Generate Draft Node]:::node
    generate_draft --> critique[Critique Node]:::node
    
    critique --> should_revise{Should Revise?}
    should_revise -- "Yes" --> generate_draft
    should_revise -- "No / Approved" --> user_approval[User Approval Node - INTERRUPT]:::node
    
    user_approval --> feedback_loop{Feedback Loop?}
    feedback_loop -- "Has Feedback" --> generate_draft
    feedback_loop -- "Approved" --> finalize[Finalize Node]:::node
    finalize --> END((END))
```

### B. Product Manager Subgraphs
Divided into Phase A (PRD creation & review) and Phase B (Jira & Slack initial setup).

#### PM Phase A (PRD Creation)
```mermaid
graph TD
    classDef node fill:#1f2335,stroke:#ff9e64,stroke-width:1.5px,color:#fff;

    START((START)) --> research[Research Node]:::node
    research --> write_prd[Write PRD Node]:::node
    write_prd --> user_approval[User Approval Node - INTERRUPT]:::node
    
    user_approval --> should_revise{Should Revise?}
    should_revise -- "Has Feedback" --> write_prd
    should_revise -- "Approved" --> finalize[Finalize Node]:::node
    finalize --> END((END))
```

#### PM Phase B (Platform Setup)
```mermaid
graph TD
    classDef node fill:#1f2335,stroke:#ff9e64,stroke-width:1.5px,color:#fff;

    START((START)) --> slack_channel[Create Slack Channel]:::node
    slack_channel --> jira_epic[Create Jira Epic]:::node
    jira_epic --> jira_tickets[Create Jira Tickets]:::node
    jira_tickets --> notify_slack[Notify Slack Node]:::node
    notify_slack --> END((END))
```

---

### C. Architect Subgraph
Generates system designs, validates database schemas, and contains sequential human-in-the-loop checkpoints for Schema, API, and directory layouts.

```mermaid
graph TD
    classDef node fill:#1f2335,stroke:#bb9af7,stroke-width:1.5px,color:#fff;

    START((START)) --> research[Research & Competitor Analysis]:::node
    research --> draft[Design Draft Generation]:::node
    draft --> validate[Validate Design - Schema & API Linter]:::node
    validate --> critique[Self Critique Node]:::node
    
    critique --> should_revise{Needs Iteration?}
    should_revise -- "Yes (< 3 iterations)" --> draft
    should_revise -- "No" --> app_schema[Approve DB Schema - INTERRUPT]:::node
    
    app_schema -- "Approved" --> app_api[Approve API Specifications - INTERRUPT]:::node
    app_schema -- "Rejected" --> draft
    
    app_api -- "Approved" --> app_structure[Approve Directory Structure - INTERRUPT]:::node
    app_api -- "Rejected" --> draft
    
    app_structure -- "Approved" --> finalize[Finalize Design]:::node
    app_structure -- "Rejected" --> draft
    
    finalize --> END((END))
```

---

### D. Task Breakdown Subgraph
Parses the finalized PRD and Design Document to generate discrete tickets mapped to specific SDLC roles with dependency trees.

```mermaid
graph TD
    classDef node fill:#1f2335,stroke:#73daca,stroke-width:1.5px,color:#fff;

    START((START)) --> gen_tasks[Generate Task Definitions]:::node
    gen_tasks --> parse_tasks[Parse & Sort Tasks]:::node
    parse_tasks --> END((END))
```

---

### E. Developer & QA Subgraphs (Agent Executors)
When the Dispatcher hands a task to a developer role (e.g. `backend`, `frontend`, `database_engineer`), the execution subgraph runs the development lifecycle loop.

```mermaid
graph TD
    classDef node fill:#1f2335,stroke:#7aa2f7,stroke-width:1.5px,color:#fff;

    START((START)) --> prepare[Prepare Environment & Read Context]:::node
    prepare --> generate[Generate Code / Write Implementation]:::node
    generate --> test_run[Run Unit Tests]:::node
    
    test_run --> tests_passed{All Tests Passed?}
    tests_passed -- "No" --> fix_code[Self-Correct / Fix Code]:::node
    fix_code --> test_run
    
    tests_passed -- "Yes" --> create_pr[Create Pull Request & Notify Slack]:::node
    create_pr --> END((END))
```
