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

    output_dir = _ROOT_DIR / "output"
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

    # ── Step 2: Remove stale .git directory ─────────────────────
    git_dir = output_dir / ".git"
    if git_dir.exists():
        def _force_remove(func, path, exc_info):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        try:
            shutil.rmtree(git_dir, onexc=_force_remove)
            print(f"[{agent_name}] Cleared stale .git directory.")
        except Exception:
            subprocess.run(f'rmdir /s /q "{git_dir}"', shell=True, capture_output=True)
            print(f"[{agent_name}] Cleared stale .git directory (fallback).")

    # ── Step 3: Build descriptive commit messages ────────────────
    commit_message   = _build_commit_message(agent_name, context)
    project_name     = context.get("project_name", repo_name)
    auth_url         = clone_url.replace("https://", f"https://{github_token}@")
    branch_name      = f"feature/{agent_name.lower().replace(' ', '-')}-{int(time.time())}"

    print(f"\n[{agent_name}] Commit subject: {commit_message.splitlines()[0]}")
    print(f"[{agent_name}] Branch: {branch_name}")

    # ── Step 4: Git init, add, commit, push ─────────────────────
    # We run two commits:
    #   a) An initial empty commit on `main` so the branch has a base.
    #   b) The real descriptive commit on the feature branch.
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

    git_commands = [
        "git init",
        'git config user.email "[EMAIL_ADDRESS]"',
        'git config user.name "Hamza Abbas"',
        # Switch to main and make an empty base commit just in case it's a new repo
        "git checkout -b main",
        f'git commit --allow-empty -m "{initial_msg}"',
        # Try to fetch the remote main branch. If it fails, we fall back to pushing our empty commit to initialize the remote repo.
        f"git fetch {auth_url} main || true",
        f"git reset FETCH_HEAD || git push -u {auth_url} main",
        # Now checkout the feature branch. The working directory still has all our generated code untouched!
        f"git checkout -b {branch_name}",
        "git add .",
        f'git commit -m "{commit_message}" --allow-empty',
        # Push feature branch. This commit will only contain the diff against the remote main branch!
        f"git push -u -f {auth_url} {branch_name}",
    ]

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

    if pr_res.status_code == 201:
        pr_json   = pr_res.json()
        pr_number = pr_json.get("number")
        pr_url    = pr_json.get("html_url")
        print(f"[{agent_name}] ✓ Pull Request #{pr_number} created: {pr_url}")
        return {"pr_number": pr_number, "pr_url": pr_url}
    elif pr_res.status_code == 422:
        print(f"[{agent_name}] PR creation returned 422 (may already exist): {pr_res.text}")
        return {}
    else:
        print(f"[{agent_name}] Failed to create PR: {pr_res.status_code} {pr_res.text}")
        return {}
