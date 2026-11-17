"""
Shared Jira helper for transitioning issues across workflow stages
(e.g., To Do -> In Progress -> Done) without breaking execution if Jira is
unconfigured or unreachable.
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

_STATUS_ALIASES = {
    "in progress": ("in progress", "doing", "start progress", "in_progress"),
    "done": ("done", "completed", "complete", "closed", "resolved"),
    "to do": ("to do", "todo", "open", "backlog"),
}


def _get_jira_client():
    jira_url = (os.getenv("JIRA_URL") or "").strip()
    user_email = (os.getenv("JIRA_USER_EMAIL") or "").strip()
    api_token = (os.getenv("JIRA_API_TOKEN") or "").strip()
    if not all([jira_url, user_email, api_token]):
        return None
    try:
        from jira import JIRA
        return JIRA(server=jira_url, basic_auth=(user_email, api_token))
    except Exception as e:
        print(f"[JIRA] Client init failed: {e}")
        return None


def transition_jira_issues(issue_keys: Iterable[str], target_status: str) -> None:
    """Best-effort transition for a batch of Jira issue keys."""
    keys = [k.strip() for k in issue_keys if k and not k.startswith("STUB")]
    if not keys:
        return

    jira = _get_jira_client()
    if jira is None:
        return

    wanted = target_status.strip().lower()
    candidates = _STATUS_ALIASES.get(wanted, (wanted,))

    for key in keys:
        try:
            transitions = jira.transitions(key)
            match_id: Optional[str] = None
            for tr in transitions:
                tr_name = str(tr.get("name", "")).strip().lower()
                to_name = str((tr.get("to") or {}).get("name", "")).strip().lower()
                if tr_name in candidates or to_name in candidates:
                    match_id = str(tr["id"])
                    break
            if match_id:
                jira.transition_issue(key, match_id)
                print(f"[JIRA] {key} -> {target_status}")
            else:
                avail = [tr.get("name") for tr in transitions]
                print(f"[JIRA] No '{target_status}' transition for {key} (available: {avail})")
        except Exception as e:
            print(f"[JIRA] Failed transitioning {key} -> {target_status}: {e}")
