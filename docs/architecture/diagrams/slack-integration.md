# Slack MCP Integration

This document outlines the technical architecture and implementation details for integrating the Product Manager (Phase B) with the `korotovsky/slack-mcp-server`.

## 1. The MCP Adapter & Subprocess Architecture
The Model Context Protocol (MCP) uses a client-server architecture over standard I/O (stdio) streams. 
- We installed `langchain-mcp-adapters` and the core `mcp` SDK in the Python environment.
- In `agents/src/agents/product_manager/tools/__init__.py`, we created an asynchronous context manager (`get_slack_mcp_tools`). Under the hood, this uses Python's `anyio` and `subprocess` modules to spawn a background Node.js process using `npx -y slack-mcp-server@latest`.
- Instead of HTTP, the Python script sends JSON-RPC messages directly to the Node process's `stdin` and reads responses from its `stdout`. 

## 2. Bypassing the Read-Only Safety Constraints
By default, the `korotovsky/slack-mcp-server` operates in a strictly read-only "safe mode" to prevent AI agents from accidentally spamming or mutating data. 
- To override this, we explicitly inject `SLACK_MCP_ADD_MESSAGE_TOOL="true"` into the `env` dictionary passed to the Node subprocess.
- We fetch the `SLACK_MCP_XOXC_TOKEN` and `SLACK_MCP_XOXD_TOKEN` session tokens from `.env` and pass them into the subprocess securely so it can authenticate as the specified user account.

## 3. Dynamic Tool Binding into LangChain
Once the subprocess boots, the client performs an `await session.initialize()` handshake. 
- The MCP server responds with a JSON schema defining all its capabilities (e.g., `conversations_history`, `conversations_add_message`).
- We use LangChain's `load_mcp_tools(session)` utility to parse this schema and dynamically generate native LangChain `BaseTool` objects. These tools abstract away the JSON-RPC layer entirely so the agent can invoke them natively.

## 4. Async Graph Execution (Nodes & Orchestrator)
Because MCP operates asynchronously over streams, the LangGraph nodes communicating with it must also be asynchronous.
- **Node Refactoring (`nodes.py`):** We changed `notify_slack_node` and `create_slack_channel_node` from `def` to `async def`. Inside the node, we await the context manager, search the returned tools list for `"conversations_add_message"`, and execute it using `await post_msg_tool.ainvoke({"channel_id": "...", "text": "..."})`.
- **Orchestrator Refactoring (`orchestrator/graph.py`):** Since the Phase B subgraph now relies on the `asyncio` event loop, we updated the root Orchestrator graph. We converted `pm_phase_b_stage` into an `async def` and swapped the synchronous `.invoke()` call for an `await .ainvoke()`. This ensures LangGraph seamlessly bridges the top-level synchronous dispatcher with the async MCP tools.

## Fallback Behaviors
- **Channel Creation:** Since `korotovsky/slack-mcp-server` does not expose a native tool to create new channels (`conversations_create`), the graph falls back to using the `#general` channel instead of dynamically generating dedicated channels per project.
