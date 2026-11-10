"""
Full-System Multi-Agent SDLC Benchmark & Component Evaluator
=============================================================
Runs benchmark scenarios end-to-end through the real LangGraph orchestrator (`orchestration_graph`)
and evaluates:
1. All 11 Agent Personas (`planning`, `product_manager`, `architect`, `task_breakdown`,
   `database_engineer`, `backend_dev`, `frontend_dev`, `qa`, `reviewer`, `security`, `devops`)
2. Requirements Coverage & Architectural Alignment (PRD Recall/Precision/F1, Component Recall, Tech Stack Recall)
3. Task Breakdown & DAG Topology (Role distribution, Cycle-freeness, Edge Precision/Recall/F1)
4. Output Code Quality (File count, LOC, AST/Syntax check, SQL DDL check, Test & IaC completeness)
5. GitHub & Git Agent Contributions (Branches, Conventional Commits per agent, Diffs, PRs & Reviews)
6. Jira Cloud Integration (`SCRUM` Epic & Child Ticket creation & verification)
7. PostgreSQL Persistence & Tool Calling Telemetry (`projects`, `workflows`, `tasks`, `agent_logs`, `command_executions`)
"""
import argparse
import ast
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

from dotenv import load_dotenv
load_dotenv(override=True)

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
ARCHIVE_DIR = ROOT_DIR / "output_archive"
RESULTS_DIR = ROOT_DIR / "results"


# ===========================================================================
# 1. WORKSPACE & GIT ISOLATION PER SCENARIO
# ===========================================================================

def prepare_clean_output_dir(scenario_id: str, clean: bool = True):
    """Ensures `output/<scenario_id>/` is ready before starting or resuming a scenario."""
    os.environ["USE_SCENARIO_SUBDIR"] = "1"
    os.environ["ACTIVE_SCENARIO_ID"] = scenario_id
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scen_out = OUTPUT_DIR / scenario_id
    if clean and scen_out.exists():
        shutil.rmtree(scen_out, ignore_errors=True)
    scen_out.mkdir(parents=True, exist_ok=True)
    (scen_out / "docs").mkdir(parents=True, exist_ok=True)


def archive_scenario_output(scenario_id: str, vals: dict = None) -> Path:
    """Ensures all scenario docs (Plan, PRD, Design, Tasks, Issues, Reports) are saved in `output/<scenario_id>/docs/` and copies to `output_archive/<scenario_id>/`."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scen_out = OUTPUT_DIR / scenario_id
    scen_out.mkdir(parents=True, exist_ok=True)
    docs_dir = scen_out / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    vals = vals or {}
    try:
        if (ROOT_DIR / "final_plan.md").exists() and not (docs_dir / "01_feasibility_plan.md").exists():
            shutil.copy2(ROOT_DIR / "final_plan.md", docs_dir / "01_feasibility_plan.md")
        if vals.get("prd"):
            (docs_dir / "02_prd.md").write_text(vals["prd"], encoding="utf-8")
        elif (ROOT_DIR / "final_prd.md").exists() and not (docs_dir / "02_prd.md").exists():
            shutil.copy2(ROOT_DIR / "final_prd.md", docs_dir / "02_prd.md")
        design_val = vals.get("design_doc") or vals.get("final_design_doc")
        if design_val:
            (docs_dir / "03_system_design.md").write_text(design_val, encoding="utf-8")
        elif (ROOT_DIR / "final_design.md").exists() and not (docs_dir / "03_system_design.md").exists():
            shutil.copy2(ROOT_DIR / "final_design.md", docs_dir / "03_system_design.md")
        if vals.get("workflow_tasks"):
            (docs_dir / "04_task_breakdown.json").write_text(
                json.dumps(vals["workflow_tasks"], indent=2), encoding="utf-8"
            )
            if not (docs_dir / "04_task_breakdown.md").exists():
                md_lines = [
                    "# Task Breakdown & Dependency Graph",
                    "",
                    "| # | Role | Task Description | Blocked By | Status |",
                    "|---|---|---|---|---|",
                ]
                for idx, t in enumerate(vals["workflow_tasks"], 1):
                    deps = ", ".join(t.get("blocked_by") or t.get("dependencies") or []) or "None"
                    md_lines.append(
                        f"| {idx} | `{t.get('role') or t.get('assignee_role','')}` | {t.get('description') or t.get('title','')} | {deps} | `{t.get('status') or t.get('issue_status','TODO')}` |"
                    )
                (docs_dir / "04_task_breakdown.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        if (scen_out / "jira_tickets.json").exists():
            shutil.copy2(scen_out / "jira_tickets.json", docs_dir / "05_jira_tickets.json")
        if (scen_out / "issue_board.json").exists():
            shutil.copy2(scen_out / "issue_board.json", docs_dir / "05_issue_board.json")
    except Exception as e:
        print(f"[EVALUATOR] Warning saving scenario docs: {e}")

    dest = ARCHIVE_DIR / scenario_id
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    if scen_out.exists():
        shutil.copytree(scen_out, dest, symlinks=False, ignore_dangling_symlinks=True)
    return scen_out


# ===========================================================================
# 2. METRIC HELPERS (Requirements, DAG, Code Quality, Git, Jira, DB)
# ===========================================================================

def tokenize(text: str) -> Set[str]:
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "must",
        "should", "will", "can", "are", "was", "were", "have", "has", "had",
        "user", "users", "system", "application", "app", "service", "data",
        "implement", "create", "build", "add", "setup", "configure", "support"
    }
    words = set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))
    return words - stop


def evaluate_requirements_and_architecture(scenario: dict, prd_text: str, design_text: str) -> dict:
    gold = scenario.get("gold_standard", {})
    gold_reqs = scenario.get("expected_functional_reqs") or gold.get("prd", {}).get("requirements", [])
    gold_comps = scenario.get("expected_components") or gold.get("architecture", {}).get("components", [])
    gold_stack = gold.get("architecture", {}).get("tech_stack", {})
    req_prompt = scenario.get("requirement") or scenario.get("prompt", "")

    prd_tokens = tokenize(prd_text)
    prd_sections = [s.strip() for s in re.split(r"\n(?=#+|\d+\.|- |\* )", prd_text or "") if len(s.strip()) > 25]

    matched_reqs = 0
    req_details = []
    for req in gold_reqs:
        rt = tokenize(req)
        if not rt:
            matched_reqs += 1
            req_details.append({"requirement": req, "covered": True, "overlap": 1.0})
            continue
        overlap = len(rt & prd_tokens) / len(rt)
        covered = overlap >= 0.35
        if covered:
            matched_reqs += 1
        req_details.append({"requirement": req, "covered": covered, "overlap": round(overlap, 3)})

    req_recall = matched_reqs / max(1, len(gold_reqs))
    # Precision: fraction of generated PRD bullet/requirement statements aligned with gold scope
    all_gold_tokens = tokenize(" ".join(gold_reqs) + " " + req_prompt)
    aligned_sections = 0
    for sec in prd_sections:
        st = tokenize(sec)
        if st and (len(st & all_gold_tokens) / len(st)) >= 0.20:
            aligned_sections += 1
    req_precision = aligned_sections / max(1, len(prd_sections)) if prd_sections else (1.0 if prd_text else 0.0)
    req_f1 = (2 * req_precision * req_recall / (req_precision + req_recall)) if (req_precision + req_recall) > 0 else 0.0

    # Architecture components
    design_tokens = tokenize(design_text)
    matched_comps = 0
    comp_details = []
    for comp in gold_comps:
        ct = tokenize(comp.replace("_", " "))
        overlap = (len(ct & design_tokens) / len(ct)) if ct else 1.0
        covered = overlap >= 0.35 or comp.lower().replace("_", " ").split()[0] in (design_text or "").lower()
        if covered:
            matched_comps += 1
        comp_details.append({"component": comp, "covered": covered, "overlap": round(overlap, 3)})
    comp_recall = matched_comps / max(1, len(gold_comps))

    # Tech stack recall
    matched_stack = 0
    for layer, tech in gold_stack.items():
        tt = tokenize(f"{layer} {tech}")
        if any(t in design_tokens for t in tt):
            matched_stack += 1
    stack_recall = matched_stack / max(1, len(gold_stack)) if gold_stack else 1.0

    return {
        "prd_word_count": len((prd_text or "").split()),
        "design_word_count": len((design_text or "").split()),
        "prd_requirement_recall": round(req_recall, 4),
        "prd_requirement_precision": round(req_precision, 4),
        "prd_requirement_f1": round(req_f1, 4),
        "prd_requirements_matched": f"{matched_reqs}/{len(gold_reqs)}",
        "requirement_trace": req_details,
        "arch_component_recall": round(comp_recall, 4),
        "arch_components_matched": f"{matched_comps}/{len(gold_comps)}",
        "component_trace": comp_details,
        "tech_stack_recall": round(stack_recall, 4),
    }


def evaluate_task_dag(scenario: dict, workflow_tasks: list, completed_titles: list) -> dict:
    gold_tasks = scenario.get("tasks") or scenario.get("gold_standard", {}).get("task_breakdown", [])
    roles_present = sorted({t.get("assignee_role", "unknown") for t in (workflow_tasks or [])})
    role_counts = {}
    for t in (workflow_tasks or []):
        r = t.get("assignee_role", "unknown")
        role_counts[r] = role_counts.get(r, 0) + 1

    # Check cycle-freeness via topological sort / DFS
    title_to_deps = {t.get("title", f"t_{i}"): set(t.get("dependencies", [])) for i, t in enumerate(workflow_tasks or [])}
    visited = {}
    has_cycle = False

    def dfs(node):
        nonlocal has_cycle
        visited[node] = 1
        for dep in title_to_deps.get(node, set()):
            if dep not in title_to_deps:
                continue
            if visited.get(dep) == 1:
                has_cycle = True
            elif visited.get(dep, 0) == 0:
                dfs(dep)
        visited[node] = 2

    for n in title_to_deps:
        if visited.get(n, 0) == 0:
            dfs(n)

    # Role-level dependency edges
    title_to_role = {t.get("title", ""): t.get("assignee_role", "") for t in (workflow_tasks or [])}
    gen_role_edges = set()
    for t in (workflow_tasks or []):
        dst_role = t.get("assignee_role", "")
        for dep in t.get("dependencies", []):
            src_role = title_to_role.get(dep, "")
            if src_role and dst_role and src_role != dst_role:
                gen_role_edges.add((src_role, dst_role))

    gold_key_to_role = {}
    for gt in gold_tasks:
        r = gt.get("role") or gt.get("assignee_role", "")
        if gt.get("id"):
            gold_key_to_role[gt["id"]] = r
        if gt.get("title"):
            gold_key_to_role[gt["title"]] = r

    gold_role_edges = set()
    for gt in gold_tasks:
        dst_role = gt.get("role") or gt.get("assignee_role", "")
        deps = gt.get("depends_on") or gt.get("dependencies", [])
        for dep_key in deps:
            src_role = gold_key_to_role.get(dep_key, "")
            if src_role and dst_role and src_role != dst_role:
                gold_role_edges.add((src_role, dst_role))

    # Map canonical pipeline edges if gold uses backend/frontend/qa/devops
    tp = len(gen_role_edges & gold_role_edges)
    edge_recall = tp / max(1, len(gold_role_edges)) if gold_role_edges else 1.0
    edge_precision = tp / max(1, len(gen_role_edges)) if gen_role_edges else 1.0
    edge_f1 = (2 * edge_precision * edge_recall / (edge_precision + edge_recall)) if (edge_precision + edge_recall) > 0 else 0.0

    completion_rate = len(completed_titles or []) / max(1, len(workflow_tasks or []))

    return {
        "total_tasks_generated": len(workflow_tasks or []),
        "total_tasks_completed": len(completed_titles or []),
        "task_completion_rate": round(completion_rate, 4),
        "roles_covered": roles_present,
        "role_coverage_count": len(roles_present),
        "role_distribution": role_counts,
        "is_dag_acyclic": not has_cycle,
        "generated_role_edges": [f"{a}->{b}" for a, b in sorted(gen_role_edges)],
        "gold_role_edges": [f"{a}->{b}" for a, b in sorted(gold_role_edges)],
        "dag_edge_recall": round(edge_recall, 4),
        "dag_edge_precision": round(edge_precision, 4),
        "dag_edge_f1": round(edge_f1, 4),
    }


def evaluate_code_and_outputs(target_dir: Path) -> dict:
    ignored = {".git", "node_modules", ".next", "dist", "build", "__pycache__"}
    files_info = []
    total_loc = 0
    syntax_valid_count = 0
    syntax_checked_count = 0
    has_sql_schema = False
    sql_tables_created = 0
    has_tests = False
    has_dockerfile_or_compose = False
    has_ci_workflow = False

    if target_dir.exists():
        for p in sorted(target_dir.rglob("*")):
            if not p.is_file() or any(part in ignored for part in p.parts):
                continue
            rel = str(p.relative_to(target_dir)).replace("\\", "/")
            if rel in ("git_contributions.jsonl", "jira_tickets.json"):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = ""
            loc = len(content.splitlines())
            total_loc += loc
            ext = p.suffix.lower()

            # Check syntax
            is_valid = True
            if ext == ".py":
                syntax_checked_count += 1
                try:
                    ast.parse(content)
                    syntax_valid_count += 1
                except SyntaxError:
                    is_valid = False
            elif ext == ".json":
                syntax_checked_count += 1
                try:
                    json.loads(content)
                    syntax_valid_count += 1
                except Exception:
                    is_valid = False
            elif ext in (".ts", ".tsx", ".js", ".jsx"):
                syntax_checked_count += 1
                # Balanced braces/parens & non-empty check
                if content.strip() and abs(content.count("{") - content.count("}")) <= 2:
                    syntax_valid_count += 1
                else:
                    is_valid = False
            elif ext == ".sql":
                syntax_checked_count += 1
                tables = len(re.findall(r"CREATE\s+TABLE", content, re.IGNORECASE))
                sql_tables_created += tables
                if tables > 0 or "SELECT" in content.upper() or "INSERT" in content.upper():
                    has_sql_schema = True
                    syntax_valid_count += 1
                else:
                    is_valid = False

            if "test" in rel.lower() or "spec" in rel.lower():
                has_tests = True
            if "dockerfile" in rel.lower() or "docker-compose" in rel.lower():
                has_dockerfile_or_compose = True
            if ".github/workflows" in rel.lower():
                has_ci_workflow = True

            files_info.append({
                "path": rel,
                "loc": loc,
                "size_bytes": p.stat().st_size,
                "syntax_valid": is_valid,
            })

    syntax_rate = (syntax_valid_count / syntax_checked_count) if syntax_checked_count > 0 else 1.0
    try:
        from agents.src.shared.code_completeness import find_missing_local_imports
        broken_imports = len(find_missing_local_imports(target_dir))
    except Exception:
        broken_imports = 0
    route_files = list((target_dir / "src" / "routes").glob("*.ts")) if (target_dir / "src" / "routes").exists() else []
    has_app_tsx = (target_dir / "src" / "App.tsx").exists()

    return {
        "total_files_generated": len(files_info),
        "total_lines_of_code": total_loc,
        "syntax_checked_files": syntax_checked_count,
        "syntax_valid_files": syntax_valid_count,
        "syntax_validity_rate": round(syntax_rate, 4),
        "broken_local_imports_count": broken_imports,
        "route_modules_count": len(route_files),
        "has_frontend_app_tsx": has_app_tsx,
        "has_sql_schema": has_sql_schema,
        "sql_tables_created": sql_tables_created,
        "has_test_suite": has_tests,
        "has_docker_iac": has_dockerfile_or_compose,
        "has_ci_cd_workflow": has_ci_workflow,
        "files": files_info,
    }


def evaluate_git_and_github(target_dir: Path, repo_name: str) -> dict:
    contribs = []
    jsonl_path = target_dir / "git_contributions.jsonl"
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    contribs.append(json.loads(line))
                except Exception:
                    pass

    git_commits = []
    branches = []
    if (target_dir / ".git").exists():
        try:
            log_res = subprocess.run(
                'git log --all --pretty=format:"%H|%an|%s"',
                shell=True, cwd=str(target_dir), capture_output=True, text=True
            )
            seen_shas = set()
            for line in log_res.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) == 3 and parts[0] not in seen_shas:
                    seen_shas.add(parts[0])
                    git_commits.append({"sha": parts[0][:8], "author": parts[1], "subject": parts[2]})
            br_res = subprocess.run(
                "git branch -a", shell=True, cwd=str(target_dir), capture_output=True, text=True
            )
            branches = [b.strip().lstrip("* ").strip() for b in br_res.stdout.splitlines() if b.strip()]
        except Exception:
            pass

    conv_regex = re.compile(r"^(feat|fix|test|chore|refactor)(\([a-z0-9_-]+\))?: .+", re.IGNORECASE)
    conv_valid = sum(1 for c in git_commits if conv_regex.match(c["subject"]))
    conv_rate = conv_valid / max(1, len(git_commits)) if git_commits else 0.0

    # Check remote PRs created
    prs_created = [c for c in contribs if c.get("pr_number", 0) > 0]
    has_code_review_md = (target_dir / "CODE_REVIEW.md").exists()

    return {
        "github_repo_name": repo_name,
        "total_git_commits": len(git_commits),
        "total_branches": len(branches),
        "branches": branches,
        "commits": git_commits,
        "conventional_commit_rate": round(conv_rate, 4),
        "agent_contributions": contribs,
        "remote_prs_opened": len(prs_created),
        "pr_urls": [c.get("pr_url") for c in prs_created if c.get("pr_url")],
        "reviewer_artifact_present": has_code_review_md,
    }


def evaluate_jira_integration(target_dir: Path, state_vals: dict, expected_task_count: int) -> dict:
    epic_key = state_vals.get("jira_epic_key", "")
    ticket_keys = state_vals.get("jira_ticket_keys", [])
    jira_file = target_dir / "jira_tickets.json"
    if jira_file.exists():
        try:
            jdata = json.loads(jira_file.read_text(encoding="utf-8"))
            epic_key = epic_key or jdata.get("epic_key", "")
            ticket_keys = ticket_keys or jdata.get("ticket_keys", [])
        except Exception:
            pass

    live_epic_verified = bool(epic_key and not epic_key.startswith("STUB"))
    live_tickets = [k for k in (ticket_keys or []) if not str(k).startswith("STUB")]
    ticket_coverage = len(live_tickets) / max(1, expected_task_count)

    return {
        "jira_project_key": os.getenv("JIRA_PROJECT_KEY", "SCRUM"),
        "jira_epic_key": epic_key,
        "live_epic_created": live_epic_verified,
        "jira_ticket_keys": ticket_keys,
        "live_tickets_created_count": len(live_tickets),
        "expected_tasks_count": expected_task_count,
        "jira_ticket_coverage_rate": round(min(1.0, ticket_coverage), 4),
    }


async def evaluate_database_and_tools(project_id: int, workflow_id: int) -> dict:
    from backend.database import AsyncSessionLocal
    from backend.models import Project, Workflow, Task, AgentLogModel, CommandExecution, FileRecord
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        proj = (await db.execute(select(Project).where(Project.id == project_id))).scalars().first()
        wf = (await db.execute(select(Workflow).where(Workflow.id == workflow_id))).scalars().first()
        tasks = (await db.execute(select(Task).where(Task.workflow_id == workflow_id))).scalars().all()
        logs = (await db.execute(select(AgentLogModel).where(AgentLogModel.workflow_id == workflow_id))).scalars().all()
        cmds = (await db.execute(select(CommandExecution).where(CommandExecution.project_id == project_id))).scalars().all()
        files = (await db.execute(select(FileRecord).where(FileRecord.project_id == project_id))).scalars().all()

        tool_calls_by_name = {}
        tool_calls_by_agent = {}
        subgraph_transitions = 0
        for lg in logs:
            if lg.status == "TOOL_CALL":
                tname = lg.payload or "unknown"
                tool_calls_by_name[tname] = tool_calls_by_name.get(tname, 0) + 1
                ag = lg.requesting_agent_id or "unknown"
                tool_calls_by_agent[ag] = tool_calls_by_agent.get(ag, 0) + 1
            elif lg.status == "SUBGRAPH_NODE":
                subgraph_transitions += 1

        cmd_success = sum(1 for c in cmds if c.exit_code == 0)
        completed_db_tasks = sum(1 for t in tasks if t.status == "COMPLETED")

        return {
            "project_id": project_id,
            "workflow_id": workflow_id,
            "workflow_status": wf.status if wf else "UNKNOWN",
            "db_tasks_total": len(tasks),
            "db_tasks_completed": completed_db_tasks,
            "db_agent_logs_total": len(logs),
            "db_subgraph_transitions": subgraph_transitions,
            "db_tool_calls_total": sum(tool_calls_by_name.values()),
            "tool_calls_by_name": tool_calls_by_name,
            "tool_calls_by_agent": tool_calls_by_agent,
            "db_command_executions_total": len(cmds),
            "db_command_executions_succeeded": cmd_success,
            "command_success_rate": round(cmd_success / max(1, len(cmds)), 4) if cmds else 1.0,
            "db_file_records_total": len(files),
        }


# ===========================================================================
# 3. SINGLE SCENARIO LIVE ORCHESTRATOR EXECUTION
# ===========================================================================

async def run_scenario_evaluation(scenario: dict, resume_thread_id: str = "") -> dict:
    from backend.database import AsyncSessionLocal
    from backend.models import Project, Workflow
    from backend.telemetry import set_active_project_id, set_active_scenario_id
    from backend.websocket_manager import ws_manager
    from agents.src.orchestrator.graph import parent_workflow
    from agents.src.orchestrator.state import WorkflowState
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.types import Command
    from sqlalchemy import update

    ws_manager.main_loop = asyncio.get_running_loop()

    scen_id = scenario["id"]
    prompt = scenario.get("requirement") or scenario.get("prompt", "")
    category = scenario.get("category", "unknown")
    set_active_scenario_id(scen_id, category)

    print(f"\n{'='*80}")
    print(f"[EVALUATOR] {'Resuming' if resume_thread_id else 'Starting'} Live Full-System Run for {scen_id} ({category})")
    print(f"{'='*80}")

    prepare_clean_output_dir(scen_id, clean=not bool(resume_thread_id))

    # 1. Create Project & Workflow in Database (PostgreSQL or automatic SQLite fallback)
    from sqlalchemy import text
    from backend.database import engine, Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(text("SELECT setval('projects_id_seq', COALESCE((SELECT MAX(id) FROM projects), 1), true)"))
            await db.execute(text("SELECT setval('workflows_id_seq', COALESCE((SELECT MAX(id) FROM workflows), 1), true)"))
            await db.commit()
        except Exception:
            await db.rollback()

        proj = Project(
            title=f"Benchmark {scen_id} ({category})",
            description=prompt[:900],
            path=f"output/{scen_id}",
            current_status="IN_PROGRESS",
        )
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        project_id = proj.id

        wf = Workflow(
            project_id=project_id,
            current_state="START",
            status="RUNNING",
            next_agent="planning",
        )
        db.add(wf)
        await db.commit()
        await db.refresh(wf)
        workflow_id = wf.id

    if resume_thread_id and "-" in resume_thread_id and resume_thread_id.split("-")[0].isdigit():
        project_id = int(resume_thread_id.split("-")[0])
    set_active_project_id(str(project_id))
    thread_id = resume_thread_id or f"{project_id}-{scen_id}-{int(time.time())}"
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 150}

    initial_state = WorkflowState(
        projectId=str(project_id),
        workflowId=thread_id,
        user_req=prompt,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        prd="",
        final_design_doc="",
        final_file_changes=[],
        agent_logs=[],
        human_interventions=[],
        workflow_tasks=[],
    )

    start_ts = time.time()
    stage_timings = []
    interrupts_handled = []
    error_occurred = None

    current_input = None if resume_thread_id else initial_state
    max_turns = 25

    async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
        await checkpointer.setup()
        orchestration_graph = parent_workflow.compile(checkpointer=checkpointer)

        for turn in range(max_turns):
            turn_t0 = time.time()
            try:
                async for event in orchestration_graph.astream(current_input, config=config):
                    for node_name, node_out in event.items():
                        if node_name != "__interrupt__":
                            elapsed_node = round(time.time() - turn_t0, 2)
                            print(f"  -> [STAGE DONE] {node_name} ({elapsed_node}s)")
                            stage_timings.append({"stage": node_name, "elapsed_sec": elapsed_node, "turn": turn})
                            turn_t0 = time.time()
            except Exception as e:
                error_occurred = str(e)
                print(f"  [ERROR] Exception on turn {turn}: {e}")
                break

            state_snap = await orchestration_graph.aget_state(config)
            if not state_snap.next:
                print(f"  [ORCHESTRATOR] Workflow {scen_id} reached END cleanly on turn {turn}!")
                break

            # Inspect interrupts and auto-approve / answer
            has_interrupt = False
            interrupt_val = None
            if state_snap.tasks:
                for t in state_snap.tasks:
                    if t.interrupts:
                        has_interrupt = True
                        interrupt_val = t.interrupts[0].value
                        break

            if has_interrupt:
                itype = interrupt_val.get("type", "unknown") if isinstance(interrupt_val, dict) else "unknown"
                interrupts_handled.append({"turn": turn, "type": itype, "next": list(state_snap.next)})
                if itype == "clarification":
                    questions = interrupt_val.get("questions", [])
                    ans = "\n".join(
                        f"Q{i+1}: Follow standard production best practices as specified in the prompt."
                        for i in range(len(questions))
                    ) or "Proceed with standard production architecture."
                    current_input = Command(resume=ans)
                else:
                    current_input = Command(resume="approve")
            else:
                current_input = None

        final_snap = await orchestration_graph.aget_state(config)
        vals = final_snap.values if final_snap and final_snap.values else {}

    total_duration = round(time.time() - start_ts, 2)

    # Mark workflow completed in DB
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Workflow)
            .where(Workflow.id == workflow_id)
            .values(status="COMPLETED" if not error_occurred else "PARTIAL", current_state="END")
        )
        await db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(current_status="COMPLETED" if not error_occurred else "PARTIAL")
        )
        await db.commit()

    # Wait briefly for any async fire-and-forget telemetry DB tasks to flush
    await asyncio.sleep(2.0)

    # Archive scenario output directory (including all docs in output_archive/<scen_id>/docs/)
    archived_dir = archive_scenario_output(scen_id, vals)

    # Compute all 6 evaluation dimensions
    req_arch_metrics = evaluate_requirements_and_architecture(
        scenario, vals.get("prd", ""), vals.get("final_design_doc", "")
    )
    dag_metrics = evaluate_task_dag(
        scenario, vals.get("workflow_tasks", []), vals.get("completed_task_titles", [])
    )
    code_metrics = evaluate_code_and_outputs(archived_dir)
    git_metrics = evaluate_git_and_github(archived_dir, vals.get("github_repo_name", ""))
    jira_metrics = evaluate_jira_integration(
        archived_dir, vals, len(vals.get("workflow_tasks", []))
    )
    db_tool_metrics = await evaluate_database_and_tools(project_id, workflow_id)

    report = {
        "scenario_id": scen_id,
        "category": category,
        "complexity": scenario.get("complexity", "medium"),
        "thread_id": thread_id,
        "total_duration_sec": total_duration,
        "error": error_occurred,
        "stages_executed": stage_timings,
        "interrupts_handled_count": len(interrupts_handled),
        "requirements_and_architecture": req_arch_metrics,
        "task_breakdown_and_dag": dag_metrics,
        "code_and_output_quality": code_metrics,
        "git_and_github_contributions": git_metrics,
        "jira_integration": jira_metrics,
        "database_and_tool_telemetry": db_tool_metrics,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / f"full_eval_{scen_id}.json"
    out_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[EVALUATOR] Saved full multi-component evaluation to {out_file}")
    return report


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="data/splits/test.json", help="Path to split JSON")
    parser.add_argument("--scenario-id", default="", help="Optional specific scenario ID to run")
    parser.add_argument("--resume-thread-id", default="", help="Optional thread_id to resume from checkpoint")
    parser.add_argument("--limit", type=int, default=0, help="Max scenarios to run (0 = all)")
    args = parser.parse_args()

    split_path = ROOT_DIR / args.split
    scenarios = json.loads(split_path.read_text(encoding="utf-8"))
    if args.scenario_id:
        scenarios = [s for s in scenarios if s["id"] == args.scenario_id]
    if args.limit > 0:
        scenarios = scenarios[:args.limit]

    summary_path = RESULTS_DIR / "full_system_evaluation_summary.json"
    existing_reports = {}
    if summary_path.exists():
        try:
            prev = json.loads(summary_path.read_text(encoding="utf-8"))
            for r in prev.get("scenario_reports", []):
                existing_reports[r["scenario_id"]] = r
        except Exception:
            pass

    for scen in scenarios:
        rep = await run_scenario_evaluation(scen, resume_thread_id=args.resume_thread_id)
        existing_reports[scen["id"]] = rep
        all_reps = list(existing_reports.values())
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "scenarios_evaluated": len(all_reps),
            "scenario_reports": all_reps,
        }
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
