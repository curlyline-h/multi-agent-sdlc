# Slack SDK Integration Documentation

## Architecture Overview
The Slack integration in Phase B of the Product Manager subgraph is built on the official `slack_sdk` library, specifically using the `WebClient` for synchronous HTTP interaction. This architecture replaces the previous experimental MCP (Model Context Protocol) Node.js server to ensure reliability, standard HTTP exception handling, and native Python compatibility within LangGraph.

## Configuration
The integration authenticates using a standard Bot User OAuth Token.
- `SLACK_BOT_TOKEN`: The `xoxb-` prefixed token generated via the Slack API Dashboard.

### OAuth Scope Requirements
To execute the required graph steps, the underlying bot token must be granted the following User/Bot Token Scopes:
- `channels:manage`: Required for the `conversations.create` endpoint to provision dynamic project channels.
- `chat:write`: Required for the `chat.postMessage` endpoint to publish kickoff summaries.

## LangGraph Node Implementations

### Migration from Async to Sync
Because the `slack_sdk` WebClient executes synchronous HTTP requests, the wrapper nodes in `agents/src/agents/product_manager/nodes.py` (`create_slack_channel_node` and `notify_slack_node`), as well as the orchestrator stage (`pm_phase_b_stage`), were refactored from `async def` to standard `def` functions. This aligned the Slack execution model with the rest of the synchronous multi-agent pipeline.

### 1. `create_slack_channel_node`
**Purpose:** Provisions a dedicated communication channel for the newly generated AI project.
- Receives the `state.project_name` from the orchestration state.
- Invokes the `create_slack_channel` tool.
- Handles `name_taken` or `missing_scope` exceptions by gracefully falling back to returning `#general` as the `slack_channel_id`.

### 2. `notify_slack_node`
**Purpose:** Compiles the system state into a formatted Markdown report and pushes it to the designated channel.
- Extracts `jira_epic_key` and `jira_ticket_keys`.
- Constructs a dynamic URL pointing to the Atlassian browse instance using the `JIRA_URL` environment variable.
- Uses Slack's `mrkdwn` formatting to build a structured payload.
- Invokes the `post_slack_message` tool.

## SDK Tool Implementations
Located in `agents/src/agents/product_manager/tools/__init__.py`.

### `create_slack_channel`
- Initializes `WebClient(token=os.getenv("SLACK_BOT_TOKEN"))`.
- Calls `client.conversations_create(name=channel_name)`.
- Returns the provisioned `channel_id`. Note: Slack requires explicit API channel IDs (e.g., `C0BJ0C40TF0`) rather than `#channel-name` for subsequent API calls.

### `post_slack_message`
- Receives the `channel_id` and Markdown string.
- Calls `client.chat_postMessage(channel=channel_id, text=message)`.
- Implements ASCII encoding fallback in exception `print()` statements to prevent Windows `charmap` UnicodeEncodeErrors when logging exceptions containing Emojis.
