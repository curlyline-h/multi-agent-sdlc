# Multi-Agent SDLC — Agent Capabilities & Tool Matrix

This document defines the exact tools and supported verification toolchains available to each specialized agent in the pipeline. The Architect Agent uses this matrix when selecting tech stacks and designing directory structures.

## 1. Shared Workspace Tools (Available to All Coding & Verification Agents)
- `write_file(file_path, content)`: Creates or overwrites a file inside the active project workspace.
- `replace_file_content(file_path, target_string, replacement_string)`: Performs exact block replacements in an existing file.
- `read_file_range(file_path, start_line, end_line)`: Reads specific line ranges from a workspace file.
- `list_directory(path)`: Lists files and subdirectories in the project workspace.
- `semantic_code_search(query)`: Searches code symbols and text across the active workspace.
- `run_terminal_command(command)`: Runs shell commands inside the project workspace with timeout protection.
- `fetch_server_logs(lines)`: Reads recent application/server log output.
- `rag_search(query, k)`: Queries the internal knowledge base for reference architectures and ADRs.
- `search_web(query)`: Searches the web for documentation and package references.

## 2. Specialized Agent Toolbelts & Supported Build Verifiers
- **Planning Agent (`planner`)**: `rag_search`, `search_web`, `parse_structured_output`
- **Product Manager (`product_manager`)**: `rag_search`, `create_jira_epic`, `create_jira_tickets`, `create_slack_channel`, `post_slack_message`
- **Architect (`architect`)**: `rag_search`, `validate_schema` (SQL/DDL sanity check), `lint_api_spec` (REST/HTTP contract check)
- **Database Engineer (`database_engineer`)**: `create_project_database` (PostgreSQL), `run_migrations` (`output/db/*.sql`), `validate_schema_diff`
  - *Note*: Omit `database_engineer` tasks for client-side-only apps, browser games, or static sites (`Database: None`).
- **Backend Developer (`backend_dev`)**: `code_linter`, `run_unit_tests`, `db_schema_inspector`, plus all shared workspace tools.
- **Frontend Developer (`frontend_dev`)**: `api_schema_fetcher`, `frontend_linter`, `run_component_tests`, `visual_browser_check`, plus all shared workspace tools.
- **QA Engineer (`qa`)**: `run_test_suite`, `api_integration_tester`, `visual_browser_tester`, `generate_bug_report`, plus all shared workspace tools.
- **Code Reviewer (`reviewer`)**: `run_complexity_analysis` (static metrics + git diff audit), `leave_pr_comment`, `merge_pull_request`, plus all shared workspace tools.
- **Security Engineer (`security`)**: `run_sast_scanner` (Bandit + secret scan), `check_dependencies` (`npm audit` / `pip-audit`), `file_security_ticket`.
- **DevOps Engineer (`devops`)**: `validate_iac_config` (`docker compose config`), `run_deployment`, `health_check_ping`, `push_github_actions`.

## 3. Natively Verified Build Toolchains (`verifier.py`)
- **Node.js / TypeScript / JavaScript**: `package.json`, `tsconfig.json` (`tsc --noEmit`, `npm run build`, `node --check`, Vite, Next.js, React, Three.js)
- **Python**: `pyproject.toml`, `requirements.txt` (`py_compile`, `ruff`, `pytest`, FastAPI, Flask, Django)
- **Java / Kotlin**: `pom.xml`, `build.gradle` (`mvn compile`, `gradle compileJava`, JUnit)
- **Go**: `go.mod` (`go build ./...`, `go vet ./...`, `go test ./...`)
- **Rust**: `Cargo.toml` (`cargo check`, `cargo test`)
- **.NET / C#**: `*.csproj` (`dotnet build`)
