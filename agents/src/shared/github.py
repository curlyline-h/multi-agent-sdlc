import os
import subprocess
import requests
import stat
import shutil
import time
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parents[3]


def _build_commit_message(agent_name: str, context: dict) -> str:
    """
    Build a rich, conventional-commit-style message from the push context.

    context keys (all optional):
        project_name      – human-readable project name
        task_title        – the task that triggered this push
        task_description  – short description of the task
        completed_tasks   – list[str] of all completed task titles so far
        files_changed     – list[str | dict] of file paths that were written
        scope             – module scope (e.g. "api", "ui", "db", "devops")
        iteration         – iteration number if in a feedback loop
        linter_clean      – bool, True if linter passed
    """
    project_name    = context.get("project_name", "")
    task_title      = context.get("task_title", "")
    task_desc       = context.get("task_description", "")
    completed_tasks = context.get("completed_tasks", [])
    files_changed   = context.get("files_changed", [])
    scope           = context.get("scope", "")
    iteration       = context.get("iteration", None)
    linter_clean    = context.get("linter_clean", None)

    # ── Derive conventional-commit type from agent role ─────────
    agent_lower = agent_name.lower()
    if "frontend" in agent_lower or "ui" in agent_lower:
        commit_type = "feat(ui)"
    elif "backend" in agent_lower or "api" in agent_lower:
        commit_type = "feat(api)"
    elif "database" in agent_lower or "db" in agent_lower:
        commit_type = "feat(db)"
    elif "devops" in agent_lower or "infra" in agent_lower:
        commit_type = "chore(infra)"
    elif "qa" in agent_lower or "test" in agent_lower:
        commit_type = "test"
    elif "review" in agent_lower:
        commit_type = "refactor"
    elif "security" in agent_lower:
        commit_type = "fix(security)"
    else:
        commit_type = "feat"

    if scope and f"({scope})" not in commit_type:
        commit_type = f"{commit_type.split('(')[0]}({scope})"

    # ── Short subject line (≤72 chars) ──────────────────────────
    subject_parts = []
    if task_title:
        subject_parts.append(task_title)
    elif project_name:
        subject_parts.append(f"Implement {project_name} changes")
    else:
        subject_parts.append(f"Code update by {agent_name}")

    if iteration is not None:
        subject_parts.append(f"[iter-{iteration}]")

    subject = " ".join(subject_parts)
    if len(subject) > 68:
        subject = subject[:65] + "..."

    # ── Body ─────────────────────────────────────────────────────
    body_lines = []

    if project_name:
        body_lines.append(f"Project : {project_name}")
    body_lines.append(f"Agent   : {agent_name}")
    body_lines.append(f"Time    : {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")

    if task_desc:
        body_lines.append("")
        body_lines.append("Task description")
        body_lines.append("-" * 16)
        # wrap at 72 chars
        for word in task_desc.split():
            if not body_lines[-1] or body_lines[-1] == "-" * 16:
                body_lines.append(word)
            elif len(body_lines[-1]) + 1 + len(word) <= 72:
                body_lines[-1] += " " + word
            else:
                body_lines.append(word)

    if files_changed:
        body_lines.append("")
        body_lines.append("Files changed")
        body_lines.append("-" * 13)
        for fc in files_changed[:20]:  # cap at 20 to keep message sane
            path = fc.get("path", str(fc)) if isinstance(fc, dict) else str(fc)
            body_lines.append(f"  • {path}")
        if len(files_changed) > 20:
            body_lines.append(f"  … and {len(files_changed) - 20} more file(s)")

    if completed_tasks:
        body_lines.append("")
        body_lines.append("Completed sprint tasks")
        body_lines.append("-" * 22)
        for ct in completed_tasks[-10:]:  # last 10
            body_lines.append(f"  ✓ {ct}")

    if linter_clean is True:
        body_lines.append("")
        body_lines.append("✅ Linter: passed")
    elif linter_clean is False:
        body_lines.append("")
        body_lines.append("⚠️  Linter: reported issues (see CI)")

    body = "\n".join(body_lines)
    return f"{commit_type}: {subject}\n\n{body}"


def _build_pr_body(agent_name: str, branch_name: str, context: dict) -> str:
    """Generate a rich markdown PR description."""
    project_name    = context.get("project_name", "AI-Generated Project")
    task_title      = context.get("task_title", "")
    task_desc       = context.get("task_description", "")
    completed_tasks = context.get("completed_tasks", [])
    files_changed   = context.get("files_changed", [])
    linter_clean    = context.get("linter_clean", None)

    lines = [
        f"## 🤖 Automated Pull Request — {agent_name}",
        "",
        f"**Project:** `{project_name}`  ",
        f"**Branch:** `{branch_name}`  ",
        f"**Generated at:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        "",
    ]

    if task_title:
        lines += [
            "### 📋 Task",
            f"**{task_title}**",
            "",
        ]
    if task_desc:
        lines += [
            "### 📝 Description",
            task_desc,
            "",
        ]

    if files_changed:
        lines += ["### 📁 Files Changed", ""]
        for fc in files_changed[:30]:
            path = fc.get("path", str(fc)) if isinstance(fc, dict) else str(fc)
            lines.append(f"- `{path}`")
        if len(files_changed) > 30:
            lines.append(f"- _…and {len(files_changed) - 30} more_")
        lines.append("")

    if completed_tasks:
        lines += ["### ✅ Sprint Tasks Completed in This Run", ""]
        for ct in completed_tasks:
            lines.append(f"- [x] {ct}")
        lines.append("")

    # Quality gates section
    lines += ["### 🔍 Quality Gates", ""]
    lines.append(f"| Gate | Status |")
    lines.append(f"|------|--------|")
    linter_status = "✅ Passed" if linter_clean is True else ("⚠️ Issues found" if linter_clean is False else "— N/A")
    lines.append(f"| Linter | {linter_status} |")
    lines.append(f"| Code Review | Pending |")
    lines.append(f"| Security Scan | Pending |")
    lines.append(f"| QA Tests | Pending |")
    lines.append("")

    lines += [
        "---",
        "_This PR was automatically generated by the AI SDLC Orchestrator pipeline._",
        "_Please review the changes and merge when ready._",
    ]

    return "\n".join(lines)


def push_to_github(repo_name: str, agent_name: str, context: dict = None) -> dict:
    """
    Creates a GitHub repo via the API and pushes the output/ directory.

    Args:
        repo_name  : Name of the GitHub repo to push to.
        agent_name : The name of the agent doing the push.
        context    : Optional dict with descriptive metadata:
                     project_name, task_title, task_description,
                     completed_tasks, files_changed, scope,
                     iteration, linter_clean.
    """
    context = context or {}

    if not repo_name:
        print(f"[{agent_name}] No github_repo_name set. Skipping GitHub push.")
        return {}

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print(f"[{agent_name}] GITHUB_TOKEN not found in environment. Skipping GitHub push.")
        return {}

    from agents.src.shared.tools import get_output_dir
    output_dir = get_output_dir()
    if not output_dir.exists():
        print(f"[{agent_name}] No output directory found. Skipping GitHub push.")
        return {}

    # ── Step 1: Create / verify the GitHub repository ──────────
    print(f"\n[{agent_name}] Creating/verifying repository: {repo_name}...")
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    api_res = requests.post(
        "https://api.github.com/user/repos",
        headers=headers,
        json={"name": repo_name, "private": False, "auto_init": False},
    )

    user_login = None
    if api_res.status_code == 201:
        clone_url  = api_res.json().get("clone_url")
        user_login = api_res.json().get("owner", {}).get("login")
        print(f"[{agent_name}] Repository created: {clone_url}")
    elif api_res.status_code == 422:
        print(f"[{agent_name}] Repository already exists. Re-using.")
        user_res   = requests.get("https://api.github.com/user", headers=headers)
        user_login = user_res.json().get("login")
        clone_url  = f"https://github.com/{user_login}/{repo_name}.git"
    else:
        print(f"[{agent_name}] Failed to create repo: {api_res.status_code} {api_res.text}")
        return {}

    # ── Step 2: Initialize or reuse scenario .git directory ─────
    git_dir = output_dir / ".git"
    is_new_git = not git_dir.exists()

    # ── Step 3: Build descriptive commit messages ────────────────
    # If files_changed wasn't explicitly passed, auto-discover recently written files in output_dir
    if not context.get("files_changed"):
        discovered = []
        for p in sorted(output_dir.rglob("*")):
            if p.is_file() and not any(ig in p.parts for ig in (".git", "node_modules", ".next", "dist", "__pycache__")):
                discovered.append(str(p.relative_to(output_dir)).replace("\\", "/"))
        context["files_changed"] = discovered

    commit_message   = _build_commit_message(agent_name, context)
    project_name     = context.get("project_name", repo_name)
    auth_url         = clone_url.replace("https://", f"https://x-access-token:{github_token}@")

    # Discover linked Jira Ticket & GitHub Issue for this agent role from output/issue_board.json
    linked_issues = []
    issue_board_path = output_dir / "issue_board.json"
    if issue_board_path.exists():
        try:
            import json as _json
            ib = _json.loads(issue_board_path.read_text(encoding="utf-8"))
            role_hint = context.get("scope", "") or agent_name.lower()
            for iss in ib.get("issues", []):
                r = iss.get("assignee_role", "").lower()
                if r in agent_name.lower() or (role_hint == "api" and r == "backend") or (role_hint == "ui" and r == "frontend") or (role_hint == "db" and "database" in r) or (role_hint == "infra" and "devops" in r):
                    linked_issues.append(iss)
        except Exception:
            pass

    issue_slug = ""
    issue_refs = []
    for iss in linked_issues:
        jkey = iss.get("jira_ticket_key", "")
        gh_num = iss.get("github_issue_number")
        if jkey and not issue_slug:
            issue_slug = f"{jkey.lower()}-"
        if jkey:
            issue_refs.append(f"Refs {jkey}")
        if gh_num:
            issue_refs.append(f"Closes #{gh_num}")

    if issue_refs:
        ref_line = ", ".join(dict.fromkeys(issue_refs))
        lines = commit_message.splitlines()
        lines[0] = f"{lines[0]} ({ref_line})"
        commit_message = "\n".join(lines)

    branch_name = f"feature/{issue_slug}{agent_name.lower().replace(' ', '-')}-{int(time.time())}"

    print(f"\n[{agent_name}] Commit subject: {commit_message.splitlines()[0]}")
    print(f"[{agent_name}] Branch: {branch_name}")

    # ── Step 4: Git init, add, commit, push ─────────────────────
    initial_msg = (
        f"chore(init): initialise {project_name} repository\n\n"
        f"Created by {agent_name} on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}."
    )

    # Automatically generate a .gitignore to prevent committing node_modules, logs, etc.
    gitignore_path = output_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_content = """
node_modules/
.next/
dist/
build/
coverage/
*.log
.env
__pycache__/
*.pyc
venv/
env/
.pytest_cache/
.playwright/
test-results/
playwright-report/
blob-report/
"""
        gitignore_path.write_text(gitignore_content.strip(), encoding="utf-8")
        print(f"[{agent_name}] Generated .gitignore to prevent committing useless files.")

    # Write commit message to a temp file outside tracked files to avoid shell-escaping issues with newlines/quotes
    msg_file = _ROOT_DIR / ".tmp_commit_msg.txt"
    msg_file.write_text(commit_message, encoding="utf-8")

    git_commands = []
    if is_new_git:
        git_commands.extend([
            "git init",
            'git config user.email "hamzaabbas47698@gmail.com"',
            'git config user.name "HamzaAbbas1122"',
            "git checkout -b main",
            f'git commit --allow-empty -m "{initial_msg}"',
            f"git push -u -f {auth_url} main",
        ])
    else:
        git_commands.extend([
            'git config user.email "hamzaabbas47698@gmail.com"',
            'git config user.name "HamzaAbbas1122"',
        ])

    git_commands.extend([
        f"git checkout -B {branch_name}",
        "git add .",
        f'git commit -F "{msg_file}" --allow-empty',
        f"git push -u -f {auth_url} {branch_name}",
    ])

    for cmd in git_commands:
        safe_cmd = cmd.replace(github_token, "***")
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(output_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            stdout = result.stdout.strip()
            print(f"[{agent_name}] ✓ {safe_cmd}" + (f"\n    {stdout}" if stdout else ""))
        except subprocess.CalledProcessError as e:
            safe_err = e.stderr.replace(github_token, "***").strip()
            print(f"[{agent_name}] ✗ {safe_cmd}: {safe_err}")

    # Capture commit SHA
    commit_sha = ""
    try:
        sha_res = subprocess.run("git rev-parse HEAD", shell=True, cwd=str(output_dir), capture_output=True, text=True)
        commit_sha = sha_res.stdout.strip()
    except Exception:
        pass

    # ── Step 5: Create Pull Request with rich description ────────
    print(f"\n[{agent_name}] Creating descriptive Pull Request...")

    if not user_login:
        user_res   = requests.get("https://api.github.com/user", headers=headers)
        user_login = user_res.json().get("login")

    task_title = context.get("task_title", f"{agent_name} — code update")
    pr_title   = f"[{agent_name}] {task_title}"
    if len(pr_title) > 120:
        pr_title = pr_title[:117] + "..."

    pr_body = _build_pr_body(agent_name, branch_name, context)

    pr_data = {
        "title": pr_title,
        "body":  pr_body,
        "head":  branch_name,
        "base":  "main",
    }

    pr_res = requests.post(
        f"https://api.github.com/repos/{user_login}/{repo_name}/pulls",
        headers=headers,
        json=pr_data,
    )

    pr_number = 0
    pr_url = ""
    if pr_res.status_code == 201:
        pr_json   = pr_res.json()
        pr_number = pr_json.get("number", 0)
        pr_url    = pr_json.get("html_url", "")
        print(f"[{agent_name}] ✓ Pull Request #{pr_number} created: {pr_url}")
    elif pr_res.status_code == 422:
        print(f"[{agent_name}] PR creation returned 422 (may already exist): {pr_res.text}")
    else:
        print(f"[{agent_name}] Failed to create PR: {pr_res.status_code} {pr_res.text}")

    # Persist structured Git/GitHub contribution telemetry
    import json as _json
    contrib_record = {
        "agent_name": agent_name,
        "repo_name": repo_name,
        "branch_name": branch_name,
        "commit_sha": commit_sha,
        "commit_subject": commit_message.splitlines()[0] if commit_message else "",
        "files_changed_count": len(context.get("files_changed", [])),
        "linked_jira_tickets": [i.get("jira_ticket_key") for i in linked_issues if i.get("jira_ticket_key")],
        "linked_github_issues": [i.get("github_issue_number") for i in linked_issues if i.get("github_issue_number")],
        "pr_number": pr_number,
        "pr_url": pr_url,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        with open(output_dir / "git_contributions.jsonl", "a", encoding="utf-8") as cf:
            cf.write(_json.dumps(contrib_record) + "\n")
    except Exception:
        pass

    # Post contribution details (Commit SHA, Branch, PR URL, Files Changed) onto linked Jira & GitHub Issues
    if linked_issues:
        try:
            from agents.src.shared.issue_tracker import record_agent_contribution_on_issues
            record_agent_contribution_on_issues(
                repo_name=repo_name,
                agent_name=agent_name,
                active_tasks=linked_issues,
                commit_sha=commit_sha,
                branch_name=branch_name,
                pr_number=pr_number,
                pr_url=pr_url,
                files_changed=context.get("files_changed", []),
            )
        except Exception as e:
            print(f"[{agent_name}] Warning posting contribution to issues: {e}")

    try:
        from backend.telemetry import broadcast_tool_call
        broadcast_tool_call(
            "push_to_github",
            f"repo={repo_name} branch={branch_name} sha={commit_sha[:8]} pr=#{pr_number}",
            agent_role=agent_name,
        )
    except Exception:
        pass

    return {"pr_number": pr_number, "pr_url": pr_url, "commit_sha": commit_sha, "branch_name": branch_name}
