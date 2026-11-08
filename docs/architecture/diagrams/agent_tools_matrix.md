# Agent Tool Selection Matrix

To ensure our agents are capable but securely sandboxed, we need to carefully select their tools. This matrix defines exactly which **MCP Servers** (Model Context Protocol) and **Internal Python Tools** each agent gets.

## 1. Planners & Strategists
These agents do not write code. Their job is to gather information and output markdown/JSON to the state.

| Agent | MCP Tools | Internal Python Tools | Purpose |
|-------|-----------|-----------------------|---------|
| **Planning** | Web Search MCP | `rag_search`, `query_market_data` | Researching feasibility and querying internal knowledge base. |
| **Product Manager** | Web Search MCP | `rag_search`, `create_jira_epic`, `create_jira_tickets`, `create_slack_channel`, `post_slack_message` | Researching and communicating product specs and ticket tracking. |
| **Architect** | None | `rag_search`, `validate_schema`, `lint_api_spec` | Querying architecture guidelines and linting proposed system designs. |
| **Task Breakdown** | None | None | Pure reasoning based on the Architect's design document. |

---

## 2. Core Builders
These agents write code. Their file access MUST be scoped to specific directories to prevent them from destroying each other's work. They also have dynamic file reading tools for repairing and updating code context-awarely.

| Agent | MCP Tools | Internal Python Tools | Scope/Restrictions |
|-------|-----------|-----------------------|--------------------|
| **Database Engineer** | Postgres MCP, Filesystem | `run_alembic_migration`, `verify_schema_drift`, `rollback_migration` | Filesystem restricted to database model folders. Postgres MCP for schema drift checks. |
| **Backend Dev** | Filesystem MCP | `code_linter`, `run_unit_tests`, `read_file_range`, `semantic_code_search` | Filesystem strictly scoped to backend directory. Can dynamically read/search files. |
| **Frontend Dev** | Filesystem MCP | `frontend_linter`, `run_component_tests`, `visual_browser_check`, `read_file_range`, `semantic_code_search` | Filesystem strictly scoped to frontend directory. Can dynamically read/search files. |

---

## 3. Validators & Enforcers
These agents verify the builders' work and require broad read access but restricted write access.

| Agent | MCP Tools | Internal Python Tools | Scope/Restrictions |
|-------|-----------|-----------------------|--------------------|
| **QA (Tester)** | Filesystem MCP | `run_test_suite`, `api_integration_tester`, `generate_bug_report`, `visual_browser_tester` | Broad test execution and bug reporting tools. |
| **Reviewer** | GitHub MCP, Filesystem MCP | `run_complexity_analysis`, `leave_pr_comment`, `merge_pull_request` | GitHub interactions and static complexity analysis. |
| **Security** | None | `run_sast_scanner`, `check_dependencies`, `file_security_ticket` | Runs static application security testing and files vulnerability tickets. |

---

## 4. Deployment
The final agent that ships the code.

| Agent | MCP Tools | Internal Python Tools | Scope/Restrictions |
|-------|-----------|-----------------------|--------------------|
| **DevOps** | Docker MCP, GitHub MCP | `trigger_deployment`, `verify_deployment`, `rollback_deployment`, `create_infrastructure_ticket` | CI/CD pipeline triggering and rollback capabilities. |

---

> [!IMPORTANT]
> **Dynamic Context Tools (ReAct Loop)**: 
> `read_file_range` and `semantic_code_search` allow the builders to query the codebase on-demand rather than relying on massive context dumps, ensuring we don't hit token limits.
