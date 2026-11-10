"""
Issue-Driven Multi-Agent Contribution Tracker (Jira Cloud + GitHub Issues)
==========================================================================
Links every task in `workflow_tasks` to:
1. A Jira Cloud Ticket (`SCRUM-XX`) on the active project board.
2. A GitHub Issue (`#N`) on the generated project repository.

Provides lifecycle hooks for agents to:
- Sync/create GitHub Issues for all tasks in `workflow_tasks`.
- Claim an issue when dispatched (`To Do` -> `In Progress` + comment on Jira & GitHub Issue).
- Log code contributions (Commit SHA, Branch, Files Changed, PR URL) onto the Jira Ticket & GitHub Issue.
- Complete/Close the issue (`In Progress` -> `Done` on Jira, `state="closed"` on GitHub Issue) or file a linked remediation issue when QA/Reviewer/Security rejects work.
"""
import json
import os
import time
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

_ROOT_DIR = Path(__file__).resolve().parents[3]


def _get_jira_client():
    from jira import JIRA
    jira_url = os.getenv("JIRA_URL")
    user_email = os.getenv("JIRA_USER_EMAIL")
    api_token = os.getenv("JIRA_API_TOKEN")
    if not all([jira_url, user_email, api_token]):
        return None
    try:
        return JIRA(server=jira_url, basic_auth=(user_email, api_token))
    except Exception as e:
        print(f"[IssueTracker] Could not initialize Jira client: {e}")
        return None


def _get_github_headers_and_user() -> tuple[dict, Optional[str]]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return {}, None
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        r = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        if r.status_code == 200:
            return headers, r.json().get("login")
    except Exception:
        pass
    return headers, None


def ensure_github_repo_and_issues(repo_name: str, workflow_tasks: List[Dict[str, Any]], jira_epic_key: str = "") -> List[Dict[str, Any]]:
    """
    Ensures the target GitHub repository exists and creates a GitHub Issue (#N)
    for each task in `workflow_tasks` (if not already created), binding both
    `jira_ticket_key` and `github_issue_number` directly onto each task dict.
    """
    if not repo_name or not workflow_tasks:
        return workflow_tasks

    headers, user_login = _get_github_headers_and_user()
    if not user_login:
        return workflow_tasks

    # 1. Ensure repo exists on GitHub
    try:
        requests.post(
            "https://api.github.com/user/repos",
            headers=headers,
            json={"name": repo_name, "private": False, "auto_init": False},
            timeout=15,
        )
    except Exception:
        pass

    # 2. Load jira_tickets.json if present to map SCRUM-XX keys to tasks
    from agents.src.shared.tools import get_output_dir
    output_dir = get_output_dir()
    jira_keys = []
    jira_file = output_dir / "jira_tickets.json"
    if jira_file.exists():
        try:
            jdata = json.loads(jira_file.read_text(encoding="utf-8"))
            jira_keys = jdata.get("ticket_keys", [])
            if not jira_epic_key:
                jira_epic_key = jdata.get("epic_key", "")
        except Exception:
            pass

    updated_tasks = []
    for idx, task in enumerate(workflow_tasks):
        t = dict(task)
        if idx < len(jira_keys) and not t.get("jira_ticket_key"):
            t["jira_ticket_key"] = jira_keys[idx]

        if not t.get("github_issue_number"):
            role = t.get("assignee_role", "agent")
            title = t.get("title", f"Task {idx+1}")
            jkey = t.get("jira_ticket_key", "")
            prefix = f"[{jkey}] " if jkey else ""
            gh_title = f"{prefix}[{role}] {title}"[:240]
            deps = t.get("dependencies", [])
            body_lines = [
                f"### 🎯 Issue Specification",
                f"**Assigned Agent Persona:** `{role}`",
                f"**Jira Ticket:** `{jkey or 'N/A'}` (Epic: `{jira_epic_key or 'N/A'}`)",
                f"**Priority:** `{t.get('priority', 3)}`",
                f"**Dependencies:** {', '.join(f'`{d}`' for d in deps) if deps else 'None (Ready immediately)'}",
                "",
                "### 📝 Description",
                t.get("description", "Implement requirement according to system design."),
            ]
            try:
                res = requests.post(
                    f"https://api.github.com/repos/{user_login}/{repo_name}/issues",
                    headers=headers,
                    json={
                        "title": gh_title,
                        "body": "\n".join(body_lines),
                        "labels": [role, "ai-sdlc"],
                    },
                    timeout=15,
                )
                if res.status_code == 201:
                    ij = res.json()
                    t["github_issue_number"] = ij.get("number")
                    t["github_issue_url"] = ij.get("html_url", "")
                    print(f"[IssueTracker] ✓ Created GitHub Issue #{t['github_issue_number']} for {jkey or title}")
            except Exception as e:
                print(f"[IssueTracker] Warning creating GitHub issue: {e}")

        t.setdefault("issue_status", "TODO")
        updated_tasks.append(t)

    # Save enriched issue board to output/issue_board.json
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "issue_board.json").write_text(
            json.dumps({"repo_name": repo_name, "jira_epic_key": jira_epic_key, "issues": updated_tasks}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    return updated_tasks


def transition_and_comment_on_claim(repo_name: str, active_tasks: List[Dict[str, Any]], role_name: str):
    """
    Called when `dispatcher_stage` dispatches a batch of ready issues to `role_name`.
    Transitions Jira tickets to 'In Progress' and comments on both Jira and GitHub Issues.
    """
    jira = _get_jira_client()
    headers, user_login = _get_github_headers_and_user()

    for task in (active_tasks or []):
        jkey = task.get("jira_ticket_key", "")
        gh_num = task.get("github_issue_number")
        title = task.get("title", "")
        claim_msg = (
            f"🤖 **Agent `{role_name}` claimed this issue and started implementation.**\n"
            f"- **Task:** {title}\n"
            f"- **Status:** `IN_PROGRESS`\n"
            f"- **Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
        )

        # 1. Jira transition & comment
        if jira and jkey and not str(jkey).startswith("STUB"):
            try:
                transitions = jira.transitions(jkey)
                for tr in transitions:
                    if "progress" in tr["name"].lower():
                        jira.transition_issue(jkey, tr["id"])
                        break
                jira.add_comment(jkey, claim_msg)
                print(f"[IssueTracker] ✓ Jira {jkey} -> In Progress (claimed by {role_name})")
            except Exception as e:
                print(f"[IssueTracker] Jira claim update warning on {jkey}: {e}")

        # 2. GitHub Issue comment
        if user_login and repo_name and gh_num:
            try:
                requests.post(
                    f"https://api.github.com/repos/{user_login}/{repo_name}/issues/{gh_num}/comments",
                    headers=headers,
                    json={"body": claim_msg},
                    timeout=10,
                )
            except Exception:
                pass


def record_agent_contribution_on_issues(
    repo_name: str,
    agent_name: str,
    active_tasks: List[Dict[str, Any]],
    commit_sha: str,
    branch_name: str,
    pr_number: int,
    pr_url: str,
    files_changed: List[str],
):
    """
    Called when an agent pushes code and opens a PR in `push_to_github`.
    Posts a detailed engineering contribution comment on each linked Jira Ticket and GitHub Issue.
    """
    jira = _get_jira_client()
    headers, user_login = _get_github_headers_and_user()
    files_preview = ", ".join(f"`{f}`" for f in (files_changed or [])[:10]) or "Workspace files updated"

    for task in (active_tasks or []):
        jkey = task.get("jira_ticket_key", "")
        gh_num = task.get("github_issue_number")
        comment_body = (
            f"🚀 **Code Contribution Submitted by `{agent_name}`**\n"
            f"- **Branch:** `{branch_name}`\n"
            f"- **Commit SHA:** `{commit_sha[:8] if commit_sha else 'HEAD'}`\n"
            f"- **Pull Request:** {pr_url or f'PR #{pr_number}'}\n"
            f"- **Files Touched ({len(files_changed or [])}):** {files_preview}\n"
        )

        if jira and jkey and not str(jkey).startswith("STUB"):
            try:
                jira.add_comment(jkey, comment_body)
            except Exception:
                pass

        if user_login and repo_name and gh_num:
            try:
                requests.post(
                    f"https://api.github.com/repos/{user_login}/{repo_name}/issues/{gh_num}/comments",
                    headers=headers,
                    json={"body": comment_body},
                    timeout=10,
                )
            except Exception:
                pass


def finalize_issues_after_subgraph(
    repo_name: str,
    role_name: str,
    active_tasks: List[Dict[str, Any]],
    is_rejected: bool,
    pr_number: int = 0,
):
    """
    Called when `_execute_agent_subgraph` finishes.
    If approved (`not is_rejected`), transitions Jira tickets to 'Done' and closes GitHub Issues.
    """
    jira = _get_jira_client()
    headers, user_login = _get_github_headers_and_user()
    verdict = "REJECTED (Remediation Spawned)" if is_rejected else "DONE (Verified & Completed)"

    for task in (active_tasks or []):
        jkey = task.get("jira_ticket_key", "")
        gh_num = task.get("github_issue_number")
        msg = (
            f"✅ **Issue Lifecycle Update (`{role_name}`)**\n"
            f"- **Final Verdict:** `{verdict}`\n"
            f"- **Linked PR:** `#{pr_number}`\n"
            f"- **Completed At:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
        )

        if jira and jkey and not str(jkey).startswith("STUB"):
            try:
                jira.add_comment(jkey, msg)
                if not is_rejected:
                    transitions = jira.transitions(jkey)
                    for tr in transitions:
                        if any(k in tr["name"].lower() for k in ("done", "complete", "resolve", "close")):
                            jira.transition_issue(jkey, tr["id"])
                            break
                    print(f"[IssueTracker] ✓ Jira {jkey} transitioned to DONE")
            except Exception as e:
                print(f"[IssueTracker] Jira completion transition warning on {jkey}: {e}")

        if user_login and repo_name and gh_num:
            try:
                requests.post(
                    f"https://api.github.com/repos/{user_login}/{repo_name}/issues/{gh_num}/comments",
                    headers=headers,
                    json={"body": msg},
                    timeout=10,
                )
                if not is_rejected:
                    requests.patch(
                        f"https://api.github.com/repos/{user_login}/{repo_name}/issues/{gh_num}",
                        headers=headers,
                        json={"state": "closed"},
                        timeout=10,
                    )
                    print(f"[IssueTracker] ✓ Closed GitHub Issue #{gh_num}")
            except Exception:
                pass

