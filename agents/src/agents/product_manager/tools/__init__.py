"""
Product Manager Agent — MCP and Internal Tools

Phase A tools: Web search, RAG search
Phase B tools: Jira MCP (Epic + Ticket creation), Slack MCP (Channel creation + messaging)
"""
from agents.src.shared.tools import tool
from typing import List, Dict, Any
import os
import contextlib
from dotenv import load_dotenv

# Path to .env file relative to this script
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../.env"))
load_dotenv(env_path)
# ---------------------------------------------------------------------------
# RAG Search (Internal)
# ---------------------------------------------------------------------------

@tool
def create_jira_epic(
    project_key: str,
    epic_name: str,
    description: str,
    priority: str = "High"
) -> dict:
    """
    Creates a Jira Epic for the approved project.

    Args:
        project_key: The Jira project key (e.g. 'PROJ').
        epic_name: Name of the Epic (e.g. 'User Authentication System').
        description: Full PRD summary to attach to the Epic.
        priority: 'Low', 'Medium', 'High', or 'Critical'.

    Returns:
        A dict with 'epic_key' and 'epic_url'.
    """
    from jira import JIRA

    jira_url = os.getenv("JIRA_URL")
    user_email = os.getenv("JIRA_USER_EMAIL")
    api_token = os.getenv("JIRA_API_TOKEN")

    if not all([jira_url, user_email, api_token]):
        raise ValueError("Missing Jira credentials in environment variables.")

    jira = JIRA(server=jira_url, basic_auth=(user_email, api_token))

    issue_dict = {
        'project': {'key': project_key},
        'summary': epic_name,
        'description': description,
        'issuetype': {'name': 'Epic'},
    }

    try:
        new_issue = jira.create_issue(fields=issue_dict)
        return {
            "epic_key": new_issue.key,
            "epic_url": f"{jira_url}/browse/{new_issue.key}"
        }
    except Exception as e:
        raise RuntimeError(f"Failed to create Jira Epic: {e}")


@tool
def create_jira_tickets(
    project_key: str,
    epic_key: str,
    tasks: List[Dict[str, Any]]
) -> List[str]:
    """
    Creates individual Jira tickets (Stories or Tasks) from the Task Breakdown output.

    Args:
        project_key: The Jira project key.
        epic_key: The parent Epic key to link all tickets under.
        tasks: List of task dicts from the Task Breakdown Agent.
                Each dict must have: id, title, description, assigned_to, target_files.

    Returns:
        A list of created Jira ticket keys.
    """
    from jira import JIRA

    jira_url = os.getenv("JIRA_URL")
    user_email = os.getenv("JIRA_USER_EMAIL")
    api_token = os.getenv("JIRA_API_TOKEN")

    if not all([jira_url, user_email, api_token]):
        raise ValueError("Missing Jira credentials in environment variables.")

    jira = JIRA(server=jira_url, basic_auth=(user_email, api_token))

    created_keys = []
    for task in tasks:
        issue_dict = {
            'project': {'key': project_key},
            'summary': f"[{task.get('assignee_role', 'Unassigned')}] {task.get('title', 'Task')}",
            'description': f"{task.get('description', '')}\n\nTarget Files: {', '.join(task.get('target_files', []))}",
            'issuetype': {'name': 'Task'},
        }
        if epic_key and not epic_key.startswith("STUB"):
            issue_dict['parent'] = {'key': epic_key}
        try:
            new_issue = jira.create_issue(fields=issue_dict)
            created_keys.append(new_issue.key)
        except Exception as e:
            print(f"Failed to create task {task.get('title')}: {e}")
            # Try falling back without parent key if it fails due to hierarchy mapping
            try:
                del issue_dict['parent']
                issue_dict['description'] += f"\n\n(Intended Parent Epic: {epic_key})"
                new_issue = jira.create_issue(fields=issue_dict)
                created_keys.append(new_issue.key)
            except Exception as inner_e:
                print(f"Failed to create task even without parent: {inner_e}")

    return created_keys


# ---------------------------------------------------------------------------
# Slack Tools (via Official Slack SDK)
# ---------------------------------------------------------------------------

@tool
def create_slack_channel(channel_name: str) -> dict:
    """
    Creates a new public Slack channel for the project.
    
    Args:
        channel_name: The name of the channel to create (max 80 chars, lowercase, no spaces).
        
    Returns:
        A dict with 'channel_id' and 'channel_name'.
    """
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN environment variable is not set.")

    client = WebClient(token=token)
    try:
        response = client.conversations_create(name=channel_name)
        return {
            "channel_id": response["channel"]["id"],
            "channel_name": response["channel"]["name"]
        }
    except SlackApiError as e:
        if e.response["error"] == "name_taken":
            # If taken, return the existing channel info by looking it up, or just fallback
            # For simplicity, returning error string in dict
            return {"error": f"Channel name {channel_name} is already taken.", "channel_name": channel_name}
        raise RuntimeError(f"Failed to create Slack channel: {e.response['error']}")


@tool
def post_slack_message(channel_id: str, message: str) -> dict:
    """
    Posts a message to a Slack channel.
    
    Args:
        channel_id: The ID or name of the channel (e.g. '#general' or 'C12345').
        message: The text content to post (supports Slack markdown).
        
    Returns:
        A dict with 'message_ts' (timestamp of the posted message).
    """
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN environment variable is not set.")

    client = WebClient(token=token)
    try:
        response = client.chat_postMessage(channel=channel_id, text=message)
        return {
            "message_ts": response["ts"]
        }
    except SlackApiError as e:
        raise RuntimeError(f"Failed to post Slack message: {e.response['error']}")
