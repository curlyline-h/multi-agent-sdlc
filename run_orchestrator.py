import sys
import os
import uuid
import json
import time
import asyncio
from datetime import datetime

# Ensure the agents directory is in the python path
sys.path.append(os.path.abspath("."))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents.src.orchestrator.graph import parent_workflow
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# ─────────────────────────────────────────────────────────────
# ANSI colour helpers (work on modern Windows terminals)
# ─────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BLUE   = "\033[34m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"
GRAY   = "\033[90m"

_start_time = None   # wall-clock reference for elapsed-time display
_node_counter = 0    # monotonically increasing step index


# ─────────────────────────────────────────────────────────────
# Pretty-print helpers
# ─────────────────────────────────────────────────────────────

def _ts():
    """Current time in HH:MM:SS format."""
    return datetime.now().strftime("%H:%M:%S")


def _elapsed():
    """Seconds elapsed since the pipeline started."""
    if _start_time is None:
        return 0
    return round(time.time() - _start_time)


def _divider(char="─", width=70, color=GRAY):
    print(f"{color}{char * width}{RESET}")


def _header(title, color=CYAN):
    pad = max(0, 68 - len(title))
    left = pad // 2
    right = pad - left
    _divider("═", color=color)
    print(f"{color}║{' ' * left}{BOLD}{WHITE}{title}{RESET}{color}{' ' * right}║{RESET}")
    _divider("═", color=color)


def _section(label, color=BLUE):
    print(f"\n{color}{BOLD}┌─ {label} {RESET}{color}{'─' * max(0, 65 - len(label))}┐{RESET}")


def _step(icon, msg, color=WHITE, indent=4):
    prefix = " " * indent
    print(f"{prefix}{color}{icon}  {msg}{RESET}")


def _detail(key, value, indent=7, key_color=GRAY, val_color=WHITE):
    print(f"{' ' * indent}{key_color}{key:<28}{val_color}{value}{RESET}")


def _progress_bar(done, total, width=30):
    if total == 0:
        return "[" + "░" * width + "] 0/0"
    filled = int(width * done / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * done / total)
    return f"[{GREEN}{bar}{RESET}] {done}/{total} ({pct}%)"


def _log_node_banner(node_name, step_idx):
    """Print a prominent banner every time a new graph node fires."""
    ts = _ts()
    elapsed = _elapsed()
    elapsed_str = f"{elapsed//60:02d}m{elapsed%60:02d}s elapsed"

    _divider("─")
    print(
        f"{CYAN}{BOLD}[{ts}]  STEP {step_idx:03d}  ▶  {node_name.upper()}{RESET}"
        f"   {GRAY}{elapsed_str}{RESET}"
    )
    _divider("─")


# Node descriptions shown inline so you understand what each node does
NODE_DESCRIPTIONS = {
    "pm_stage":              "Product Manager → gathering requirements, writing the PRD",
    "architect_stage":       "Architect → designing system architecture, API schema, tech stack",
    "planning_stage":        "Planning Agent → breaking design into sprint tasks",
    "task_breakdown_stage":  "Task Breakdown → splitting plan into atomic dev tasks",
    "dispatcher_stage":      "Dispatcher → routing next task batch to the right agent",
    "backend_dev_stage":     "Backend Developer → writing API routes, models, services",
    "frontend_dev_stage":    "Frontend Developer → building UI components & pages",
    "database_stage":        "Database Engineer → writing SQL schema & migrations",
    "devops_stage":          "DevOps Engineer → Dockerfile, docker-compose, CI/CD pipelines",
    "reviewer_stage":        "Code Reviewer → complexity analysis & PR review",
    "security_stage":        "Security Engineer → SAST scan & dependency audit",
    "qa_stage":              "QA Automation → generating & executing test suites",
}


def _print_node_description(node_name):
    desc = NODE_DESCRIPTIONS.get(node_name)
    if desc:
        print(f"   {GRAY}↳ {desc}{RESET}")


def _print_state_update(node_name, state_update):
    """Deeply inspect every field of the state update and print it verbosely."""
    if not state_update:
        print(f"   {GRAY}(no state changes emitted by this node){RESET}")
        return

    # LangGraph emits __INTERRUPT__ events where state_update is a tuple of
    # Interrupt objects, not a dict. Handle gracefully so we don't crash.
    if not isinstance(state_update, dict):
        print(f"   {YELLOW}⚠  Interrupt / special event received:{RESET}")
        for item in (state_update if isinstance(state_update, (list, tuple)) else [state_update]):
            print(f"   {GRAY}   {item}{RESET}")
        return

    any_printed = False

    # ── Dispatcher / task routing ──────────────────────────────
    if "active_role" in state_update and state_update["active_role"]:
        role = state_update["active_role"]
        active_tasks = state_update.get("active_tasks", [])
        _step("🎯", f"Dispatcher routed to agent: {BOLD}{YELLOW}{role.upper()}{RESET}", color=YELLOW)
        _detail("Agent role assigned:", role, key_color=GRAY)
        _detail("Tasks dispatched:", str(len(active_tasks)), key_color=GRAY)
        for i, t in enumerate(active_tasks, 1):
            title = t.get("title", "Untitled") if isinstance(t, dict) else str(t)
            desc  = t.get("description", "")[:120] if isinstance(t, dict) else ""
            role2 = t.get("assignee_role", "?") if isinstance(t, dict) else "?"
            print(f"       {GRAY}{i}. [{role2}] {WHITE}{title}{RESET}")
            if desc:
                print(f"          {GRAY}{desc}...{RESET}")
        any_printed = True

    if "workflow_tasks" in state_update:
        tasks = state_update["workflow_tasks"]
        _step("📋", f"Task queue updated — {BOLD}{len(tasks)}{RESET} tasks remaining in pipeline", color=CYAN)
        for i, t in enumerate(tasks[:5], 1):   # show first 5 to keep it manageable
            if isinstance(t, dict):
                title  = t.get("title", "Untitled")
                role3  = t.get("assignee_role", "?")
                prio   = t.get("priority", "?")
                print(f"       {GRAY}{i}. [{role3}] P{prio} — {WHITE}{title}{RESET}")
        if len(tasks) > 5:
            print(f"       {GRAY}   … and {len(tasks) - 5} more tasks{RESET}")
        any_printed = True

    if "current_task" in state_update and state_update["current_task"]:
        t = state_update["current_task"]
        title = t.get("title", "Unknown") if isinstance(t, dict) else str(t)
        desc  = t.get("description", "")[:200] if isinstance(t, dict) else ""
        role4 = t.get("assignee_role", "?") if isinstance(t, dict) else "?"
        prio  = t.get("priority", "?") if isinstance(t, dict) else "?"
        deps  = t.get("dependencies", []) if isinstance(t, dict) else []
        _step("⚙️ ", f"Executing task: {BOLD}{WHITE}{title}{RESET}", color=GREEN)
        _detail("Assigned to:", role4)
        _detail("Priority:", str(prio))
        if desc:
            _detail("Description:", desc[:120] + ("…" if len(desc) > 120 else ""))
        if deps:
            _detail("Dependencies:", ", ".join(str(d) for d in deps))
        any_printed = True

    # ── Completed tasks counter ────────────────────────────────
    if "completed_task_titles" in state_update:
        done_list = state_update["completed_task_titles"]
        _step("✅", f"Completed tasks so far: {BOLD}{GREEN}{len(done_list)}{RESET}", color=GREEN)
        if done_list:
            last = done_list[-1]
            _detail("Last completed:", str(last))
        any_printed = True

    # ── Dynamic task spawning (feedback loops) ─────────────────
    if "new_workflow_tasks" in state_update and state_update["new_workflow_tasks"]:
        new_tasks = state_update["new_workflow_tasks"]
        _step("🔄", f"{BOLD}{YELLOW}FEEDBACK LOOP{RESET} — {len(new_tasks)} new tasks dynamically spawned!", color=YELLOW)
        for t in new_tasks:
            if isinstance(t, dict):
                title = t.get("title", "Untitled")
                role5 = t.get("assignee_role", "?")
                desc  = t.get("description", "")[:100]
                print(f"       {YELLOW}+ [{role5}] {title}{RESET}")
                if desc:
                    print(f"         {GRAY}{desc}…{RESET}")
        any_printed = True

    # ── Product Manager / PRD ──────────────────────────────────
    if "prd" in state_update and state_update["prd"]:
        prd = state_update["prd"]
        _step("📄", f"PRD generated — {BOLD}{len(prd):,}{RESET} chars", color=MAGENTA)
        preview = prd.replace("\n", " ")[:250]
        print(f"       {GRAY}Preview: {preview}…{RESET}")
        any_printed = True

    if "project_name" in state_update and state_update["project_name"]:
        _step("🏷️ ", f"Project name: {BOLD}{WHITE}{state_update['project_name']}{RESET}", color=MAGENTA)
        any_printed = True

    if "prd_draft" in state_update and state_update["prd_draft"]:
        draft = state_update["prd_draft"]
        _step("📝", f"PRD draft produced — {len(draft):,} chars (pending approval)", color=MAGENTA)
        any_printed = True

    if "iteration_count" in state_update:
        _detail("Iteration count:", str(state_update["iteration_count"]))
        any_printed = True

    # ── Architect ──────────────────────────────────────────────
    if "final_design_doc" in state_update and state_update["final_design_doc"]:
        doc = state_update["final_design_doc"]
        _step("🏛️ ", f"Architecture design document finalised — {BOLD}{len(doc):,}{RESET} chars", color=CYAN)
        # Print first few lines of the doc so user can see the tech stack
        lines = [l.strip() for l in doc.split("\n") if l.strip()][:6]
        for l in lines:
            print(f"       {GRAY}{l}{RESET}")
        any_printed = True

    if "system_design_draft" in state_update and state_update["system_design_draft"]:
        draft = state_update["system_design_draft"]
        _step("✏️ ", f"System design draft — {len(draft):,} chars", color=CYAN)
        any_printed = True

    if "self_critique_notes" in state_update and state_update["self_critique_notes"]:
        notes = state_update["self_critique_notes"][:200].replace("\n", " ")
        _step("🔍", f"Self-critique notes: {GRAY}{notes}…{RESET}", color=GRAY)
        any_printed = True

    if "rag_results" in state_update and state_update["rag_results"]:
        _step("🔎", f"RAG knowledge retrieval: {len(state_update['rag_results'])} result(s)", color=GRAY)
        any_printed = True

    if "web_search_results" in state_update and state_update["web_search_results"]:
        _step("🌐", f"Web search results fetched: {len(state_update['web_search_results'])} result(s)", color=GRAY)
        any_printed = True

    # ── Planning ───────────────────────────────────────────────
    if "final_plan" in state_update and state_update["final_plan"]:
        plan = state_update["final_plan"]
        _step("🗓️ ", f"Sprint plan finalised — {BOLD}{len(plan):,}{RESET} chars", color=BLUE)
        lines = [l.strip() for l in plan.split("\n") if l.strip()][:5]
        for l in lines:
            print(f"       {GRAY}{l}{RESET}")
        any_printed = True

    # ── Backend developer ──────────────────────────────────────
    if "current_code_draft" in state_update and state_update["current_code_draft"]:
        draft = state_update["current_code_draft"]
        _step("💻", f"Backend code draft — {BOLD}{len(draft):,}{RESET} chars written", color=GREEN)
        any_printed = True

    if "final_file_changes" in state_update and state_update["final_file_changes"]:
        files = state_update["final_file_changes"]
        _step("📁", f"Files committed to output/: {BOLD}{len(files)}{RESET} file(s)", color=GREEN)
        for fc in files[:8]:
            if isinstance(fc, dict):
                path = fc.get("path", str(fc))
            else:
                path = str(fc)
            print(f"       {GRAY}  ✎ {path}{RESET}")
        if len(files) > 8:
            print(f"       {GRAY}  … and {len(files) - 8} more{RESET}")
        any_printed = True

    if "linter_errors" in state_update:
        errs = state_update["linter_errors"]
        if errs:
            _step("⚠️ ", f"Linter reported errors ({len(errs)} chars) — will feed back into next iteration", color=YELLOW)
            print(f"       {GRAY}{str(errs)[:200]}…{RESET}")
        else:
            _step("✅", "Linter passed — no errors", color=GREEN)
        any_printed = True

    if "test_failures" in state_update:
        tf = state_update["test_failures"]
        if tf:
            _step("❌", f"Test failures detected ({len(str(tf))} chars) — feeding back to developer", color=RED)
            print(f"       {GRAY}{str(tf)[:200]}…{RESET}")
        else:
            _step("✅", "No test failures from previous run", color=GREEN)
        any_printed = True

    # ── Frontend developer ─────────────────────────────────────
    if "generated_ui_code" in state_update and state_update["generated_ui_code"]:
        ui = state_update["generated_ui_code"]
        count = len(ui) if isinstance(ui, list) else 1
        _step("🎨", f"Frontend UI code written: {BOLD}{count}{RESET} file/command entries", color=MAGENTA)
        any_printed = True

    # ── Database engineer ──────────────────────────────────────
    if "migration_logs" in state_update and state_update["migration_logs"]:
        logs = state_update["migration_logs"][:300].replace("\n", " ")
        _step("🗄️ ", f"Database migration logs: {GRAY}{logs}…{RESET}", color=BLUE)
        any_printed = True

    if "schema_diff_notes" in state_update and state_update["schema_diff_notes"]:
        diff = state_update["schema_diff_notes"][:200].replace("\n", " ")
        _step("📊", f"Schema diff notes: {GRAY}{diff}…{RESET}", color=BLUE)
        any_printed = True

    # ── DevOps ─────────────────────────────────────────────────
    if "iac_validation_notes" in state_update and state_update["iac_validation_notes"]:
        notes = state_update["iac_validation_notes"][:200].replace("\n", " ")
        _step("🐳", f"IaC validation: {GRAY}{notes}…{RESET}", color=CYAN)
        any_printed = True

    if "deployment_feedback" in state_update and state_update["deployment_feedback"]:
        fb = state_update["deployment_feedback"][:200].replace("\n", " ")
        _step("🚀", f"Deployment feedback: {GRAY}{fb}…{RESET}", color=CYAN)
        any_printed = True

    if "deployment_url" in state_update and state_update["deployment_url"]:
        _step("🌍", f"Deployment URL: {BOLD}{GREEN}{state_update['deployment_url']}{RESET}", color=GREEN)
        any_printed = True

    # ── Code Reviewer ──────────────────────────────────────────
    if "complexity_report" in state_update and state_update["complexity_report"]:
        rep = state_update["complexity_report"][:200].replace("\n", " ")
        _step("📈", f"Complexity analysis: {GRAY}{rep}…{RESET}", color=BLUE)
        any_printed = True

    if "code_review_approved" in state_update:
        approved = state_update["code_review_approved"]
        icon  = "✅" if approved else "❌"
        color = GREEN if approved else RED
        label = "APPROVED" if approved else "REJECTED — changes requested"
        _step(icon, f"Code review decision: {BOLD}{color}{label}{RESET}", color=color)
        any_printed = True

    if "code_review_comments" in state_update and state_update["code_review_comments"]:
        notes = state_update["code_review_comments"]
        _detail("Reviewer feedback:", notes[:300].replace("\n", " ") + ("…" if len(notes) > 300 else ""))
        any_printed = True

    # ── Security ───────────────────────────────────────────────
    if "sast_scan_results" in state_update and state_update["sast_scan_results"]:
        sast = state_update["sast_scan_results"][:300].replace("\n", " ")
        _step("🔐", f"SAST scan results: {GRAY}{sast}…{RESET}", color=YELLOW)
        any_printed = True

    if "dependency_vulnerabilities" in state_update and state_update["dependency_vulnerabilities"]:
        dep = state_update["dependency_vulnerabilities"][:300].replace("\n", " ")
        _step("📦", f"Dependency audit: {GRAY}{dep}…{RESET}", color=YELLOW)
        any_printed = True

    if "security_approved" in state_update:
        approved = state_update["security_approved"]
        icon  = "✅" if approved else "❌"
        color = GREEN if approved else RED
        label = "APPROVED — no critical vulnerabilities" if approved else "REJECTED — critical vulnerabilities found"
        _step(icon, f"Security decision: {BOLD}{color}{label}{RESET}", color=color)
        any_printed = True

    if "security_report" in state_update and state_update["security_report"]:
        rep = state_update["security_report"][:300].replace("\n", " ")
        _detail("Security report:", rep + ("…" if len(rep) >= 300 else ""))
        any_printed = True

    if "internal_vulnerabilities" in state_update and state_update["internal_vulnerabilities"]:
        vulns = state_update["internal_vulnerabilities"]
        _step("🛡️ ", f"{len(vulns)} vulnerability/ies extracted from scan", color=RED)
        for v in vulns[:3]:
            if isinstance(v, dict):
                title = v.get("title", "?")
                sev   = v.get("severity", "?")
                mit   = v.get("mitigation", "")[:80]
                print(f"       {RED}• [{sev}] {title}{RESET}")
                if mit:
                    print(f"         {GRAY}Fix: {mit}…{RESET}")
        any_printed = True

    # ── QA ─────────────────────────────────────────────────────
    if "test_run_output" in state_update and state_update["test_run_output"]:
        out = state_update["test_run_output"]
        _step("🧪", f"Test suite execution output ({len(out):,} chars):", color=CYAN)
        # Show last few lines of test output (most informative part)
        lines = [l for l in out.split("\n") if l.strip()]
        tail  = lines[-10:] if len(lines) > 10 else lines
        for l in tail:
            print(f"       {GRAY}{l}{RESET}")
        any_printed = True

    if "all_tests_passed" in state_update:
        passed = state_update["all_tests_passed"]
        icon  = "✅" if passed else "❌"
        color = GREEN if passed else RED
        label = "All tests passed! ✓" if passed else "Some tests failed — bugs filed, new fix tasks queued"
        _step(icon, f"QA verdict: {BOLD}{color}{label}{RESET}", color=color)
        any_printed = True

    if "discovered_bugs" in state_update and state_update["discovered_bugs"]:
        bugs = state_update["discovered_bugs"]
        _step("🐛", f"{len(bugs)} bug(s) discovered by QA:", color=RED)
        for b in bugs[:3]:
            if isinstance(b, dict):
                title  = b.get("title", "?")
                actual = b.get("actual", "")[:80]
                print(f"       {RED}• {title}{RESET}")
                if actual:
                    print(f"         {GRAY}Actual: {actual}…{RESET}")
        any_printed = True

    # ── GitHub ─────────────────────────────────────────────────
    if "github_repo_name" in state_update and state_update["github_repo_name"]:
        _step("🐙", f"GitHub repo: {BOLD}{GREEN}{state_update['github_repo_name']}{RESET}", color=GREEN)
        any_printed = True

    if "github_pr_url" in state_update and state_update["github_pr_url"]:
        _step("🔗", f"Pull request: {BOLD}{GREEN}{state_update['github_pr_url']}{RESET}", color=GREEN)
        any_printed = True

    # ── Agent logs ─────────────────────────────────────────────
    if "agent_logs" in state_update and state_update["agent_logs"]:
        logs = state_update["agent_logs"]
        new_logs = logs[-3:] if len(logs) > 3 else logs
        _step("📜", f"Agent log entries (showing last {len(new_logs)} of {len(logs)}):", color=GRAY)
        for entry in new_logs:
            msg = str(entry)[:160].replace("\n", " ")
            print(f"       {GRAY}• {msg}{RESET}")
        any_printed = True

    if not any_printed:
        # Catch-all: dump every key we haven't handled so nothing is invisible
        for k, v in state_update.items():
            if v is not None and v != "" and v != [] and v != {}:
                val_str = str(v)
                short   = (val_str[:120] + "…") if len(val_str) > 120 else val_str
                _detail(f"{k}:", short)


# ─────────────────────────────────────────────────────────────
# Main orchestrator runner
# ─────────────────────────────────────────────────────────────

async def run_orchestrator_async():
    global _start_time, _node_counter

    _header("AI SDLC ORCHESTRATOR")
    print(f"   {GRAY}Multi-agent software development pipeline{RESET}")
    print(f"   {GRAY}Every step, tool call, and decision will be printed below.{RESET}\n")

    session_file = ".active_session.json"
    thread_id    = None
    user_req     = None
    completed    = False

    # ── Load or create session ─────────────────────────────────
    _section("Session Management", color=BLUE)
    if os.path.exists(session_file):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                sess      = json.load(f)
                thread_id = sess.get("thread_id")
                user_req  = sess.get("user_req")
                completed = sess.get("completed", False)
            status_label = f"{GREEN}COMPLETED{RESET}" if completed else f"{YELLOW}IN PROGRESS{RESET}"
            print(f"   Found saved session  [{status_label}]")
            _detail("Thread ID:", thread_id or "?")
            _detail("Request:",   (user_req or "")[:80])
        except Exception as e:
            print(f"   {RED}Could not read session file: {e}{RESET}")
    else:
        print(f"   {GRAY}No saved session found — will start fresh.{RESET}")

    if thread_id:
        status_label2 = "[COMPLETED]" if completed else "[IN PROGRESS]"
        resume = input(
            f"\n{YELLOW}Session found: {status_label2} '{(user_req or '')[:55]}…'\n"
            f"Resume this session? (Y/n): {RESET}"
        ).strip().lower()
        if resume == "n":
            thread_id = user_req = None
            completed = False
            print(f"   {GRAY}Starting a new session.{RESET}")

    if not thread_id:
        print()
        user_req = input(f"{CYAN}What would you like to build today?\n{GRAY}(Press Enter for default To-Do app)\n{WHITE}> {RESET}")
        if not user_req.strip():
            user_req = "Create a fully functional to-do list web app with a React frontend and an Express/PostgreSQL backend."
        thread_id = str(uuid.uuid4())
        completed = False
        try:
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump({"thread_id": thread_id, "user_req": user_req, "completed": False}, f)
            print(f"   {GREEN}Session saved → {session_file}{RESET}")
        except Exception as e:
            print(f"   {YELLOW}Could not save session: {e}{RESET}")

    _detail("Thread ID:", thread_id)
    _detail("User request:", user_req[:80])

    # ── Graph setup ────────────────────────────────────────────
    config = {"configurable": {"thread_id": thread_id}}

    _checkpointer_ctx = AsyncSqliteSaver.from_conn_string("checkpoints.sqlite")
    checkpointer = await _checkpointer_ctx.__aenter__()
    await checkpointer.setup()
    orchestration_graph = parent_workflow.compile(checkpointer=checkpointer)

    _section("Graph State", color=BLUE)
    graph_state = await orchestration_graph.aget_state(config)
    is_resumed  = bool(graph_state.values)

    if is_resumed:
        checkpoint_info = graph_state.values
        completed_so_far = checkpoint_info.get("completed_task_titles", [])
        pending_tasks    = checkpoint_info.get("workflow_tasks", [])
        project_name     = checkpoint_info.get("project_name", "?")
        print(f"   {GREEN}✓ Resuming from SQLite checkpoint{RESET}")
        _detail("Project name:",     project_name)
        _detail("Tasks completed:",  str(len(completed_so_far)))
        _detail("Tasks remaining:",  str(len(pending_tasks)))
        if pending_tasks:
            print(f"   {GRAY}Next pending tasks:{RESET}")
            for t in pending_tasks[:3]:
                if isinstance(t, dict):
                    print(f"       {GRAY}• [{t.get('assignee_role','?')}] {t.get('title','?')}{RESET}")
        current_input = None
        
        # --- STATE RESTORATION PATCH ---
        # If the pipeline crashed and was resumed, LangGraph's SqliteSaver sometimes drops large text fields 
        # like final_design_doc depending on the memory state. Let's force-restore it if it's missing.
        if not checkpoint_info.get("final_design_doc") or len(checkpoint_info.get("final_design_doc").strip()) < 50:
            print(f"   {YELLOW}⚠️  final_design_doc missing from checkpoint state. Restoring from disk...{RESET}")
            import glob
            approval_files = glob.glob("schema_approval*.md")
            if approval_files:
                approval_files.sort(key=os.path.getmtime, reverse=True)
                try:
                    with open(approval_files[0], "r", encoding="utf-8") as f:
                        restored_doc = f.read()
                    # Inject it back into the graph state
                    await orchestration_graph.aupdate_state(config, {"final_design_doc": restored_doc})
                    print(f"   {GREEN}✓ Restored design doc ({len(restored_doc)} chars) from {approval_files[0]}{RESET}")
                except Exception as e:
                    print(f"   {RED}Failed to restore design doc: {e}{RESET}")
        # -------------------------------
    else:
        print(f"   {CYAN}▶ Starting fresh pipeline run{RESET}")
        current_input = {
            "user_req":              user_req,
            "workflowId":            thread_id,
            "projectId":             f"ai-agent-project-{uuid.uuid4().hex[:6]}",
            "created_at":            datetime.now(),
            "updated_at":            datetime.now(),
            "prd":                   "",
            "project_name":          "",
            "final_design_doc":      "",
            "final_file_changes":    [],
            "agent_logs":            [],
            "human_interventions":   [],
            "completed_task_titles": [],
            "workflow_tasks":        [],
            "active_tasks":          [],
            "github_repo_name":      "",
        }
        print(f"   {GRAY}Initial state seeded with {len(current_input)} fields.{RESET}")

    # ── Pipeline execution ─────────────────────────────────────
    _header("PIPELINE EXECUTION STARTING", color=GREEN)
    _start_time    = time.time()
    _node_counter  = 0

    try:
        from langgraph.types import Command

        while True:
            # ── Stream graph events ────────────────────────────
            async for event in orchestration_graph.astream(current_input, config=config):
                for node_name, state_update in event.items():
                    _node_counter += 1
                    _log_node_banner(node_name, _node_counter)
                    _print_node_description(node_name)
                    print()
                    _print_state_update(node_name, state_update)

            # ── Post-stream: check terminal or interrupt state ─
            print()
            _divider("═", color=CYAN)
            print(f"{CYAN}{BOLD}  Checking pipeline state…{RESET}")
            _divider("═", color=CYAN)

            state          = await orchestration_graph.aget_state(config)
            has_interrupts = False
            interrupts     = []

            if state.tasks:
                for task in state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        has_interrupts = True
                        interrupts.extend(task.interrupts)

            next_nodes = state.next if state.next else []
            print(f"   {GRAY}Next nodes to execute: {RESET}{CYAN}{list(next_nodes)}{RESET}")
            print(f"   {GRAY}Pending interrupt(s):  {RESET}{YELLOW}{has_interrupts}{RESET}")

            # ── Pipeline finished ──────────────────────────────
            if not state.next and not has_interrupts:
                final_state      = state.values or {}
                completed_tasks  = final_state.get("completed_task_titles", [])
                workflow_tasks   = final_state.get("workflow_tasks", [])
                has_real_tasks   = any(
                    t.get("title") != "Parse Error"
                    for t in workflow_tasks
                    if isinstance(t, dict)
                )

                elapsed = _elapsed()
                _header("PIPELINE COMPLETE", color=GREEN)
                _detail("Wall-clock time:", f"{elapsed//60}m {elapsed%60}s")
                _detail("Total nodes executed:", str(_node_counter))
                _detail("Tasks completed:", str(len(completed_tasks)))

                if completed_tasks:
                    print(f"\n{GREEN}Completed tasks:{RESET}")
                    for title in completed_tasks:
                        print(f"   {GREEN}✓ {title}{RESET}")

                if completed_tasks or not has_real_tasks:
                    print(f"\n{GREEN}{BOLD}✅  All done! Session marked as COMPLETED.{RESET}")
                    try:
                        with open(session_file, "w", encoding="utf-8") as _sf:
                            json.dump({"thread_id": thread_id, "user_req": user_req, "completed": True}, _sf)
                    except Exception:
                        pass
                else:
                    print(f"\n{YELLOW}⚠️  Pipeline exited with no completed tasks.{RESET}")
                    print(f"   {GRAY}Session preserved — run again and choose Y to retry.{RESET}")
                break

            # ── Human-in-the-loop interrupt ────────────────────
            if interrupts:
                payload = interrupts[0].value
                _header("HUMAN APPROVAL REQUIRED", color=YELLOW)
                print(f"   {YELLOW}The pipeline has paused and is waiting for your input.{RESET}\n")

                draft_content = ""
                if isinstance(payload, dict):
                    if "message" in payload:
                        print(f"   {WHITE}Message: {payload['message']}{RESET}")
                    if "section" in payload:
                        print(f"   {CYAN}Section under review: {BOLD}{payload['section']}{RESET}")
                    if "questions" in payload and payload["questions"]:
                        print(f"\n   {CYAN}The agent has the following questions:{RESET}")
                        for idx, q in enumerate(payload["questions"], 1):
                            print(f"   {idx}. {WHITE}{q}{RESET}")
                    draft_content = payload.get("draft") or payload.get("content", "")
                    doc_type = payload.get("type", "draft_review")
                elif isinstance(payload, str):
                    print(f"   {WHITE}Agent message: {payload}{RESET}")
                    draft_content  = payload
                    doc_type       = "draft_review"

                if draft_content:
                    proj_name = ""
                    if hasattr(state, "values") and state.values:
                        proj_name = state.values.get("project_name", "")
                    proj_name = "".join(c if c.isalnum() else "_" for c in proj_name).lower().strip("_")
                    filename  = f"{doc_type}_{proj_name}.md" if proj_name else f"{doc_type}.md"
                    try:
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(draft_content)
                        print(f"\n   {GREEN}👉 Draft saved to: {BOLD}{filename}{RESET}")
                        print(f"   {GRAY}Open that file in your editor to inspect before approving.{RESET}")
                    except Exception as e:
                        print(f"   {RED}Could not save draft: {e}{RESET}")
                        print(f"\n   {GRAY}--- Draft content preview (first 500 chars) ---{RESET}")
                        print(draft_content[:500])

                print()
                user_feedback = input(
                    f"{YELLOW}Your response {GRAY}(press Enter to approve, or type feedback){RESET}: "
                )
                print(f"\n   {CYAN}Resuming pipeline with your feedback…{RESET}\n")
                current_input = Command(resume=user_feedback)

            else:
                # Rare: next nodes set but no interrupt — just resume
                print(f"   {GRAY}Resuming execution…{RESET}")
                current_input = None

    except KeyboardInterrupt:
        elapsed = _elapsed()
        _header("INTERRUPTED BY USER", color=YELLOW)
        _detail("Elapsed time:", f"{elapsed//60}m {elapsed%60}s")
        _detail("Nodes executed:", str(_node_counter))
        print(f"\n   {YELLOW}Session saved — run again and choose Y to resume.{RESET}")

    except Exception as e:
        elapsed = _elapsed()
        _header("PIPELINE ERROR", color=RED)
        _detail("Elapsed time:", f"{elapsed//60}m {elapsed%60}s")
        _detail("Nodes executed:", str(_node_counter))
        print(f"\n   {RED}Error: {e}{RESET}\n")
        import traceback
        traceback.print_exc()
        print(f"\n   {YELLOW}Session preserved — run again and choose Y to resume.{RESET}")

    finally:
        try:
            await _checkpointer_ctx.__aexit__(None, None, None)
        except Exception:
            pass


def run_orchestrator():
    asyncio.run(run_orchestrator_async())

if __name__ == "__main__":
    run_orchestrator()
