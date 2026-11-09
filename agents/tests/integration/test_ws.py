"""Integration tests for WebSocket ConnectionManager broadcast and connection lifecycle."""
import os
import sys
from pathlib import Path
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Ensure repo root is on sys.path
root_dir = Path(__file__).resolve().parent.parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.websocket_manager import ConnectionManager

def test_websocket_connect_and_disconnect():
    async def _test():
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        await manager.connect("proj_123", mock_ws)
        assert "proj_123" in manager.active_connections
        assert mock_ws in manager.active_connections["proj_123"]
        mock_ws.accept.assert_awaited_once()

        manager.disconnect("proj_123", mock_ws)
        assert "proj_123" not in manager.active_connections
    asyncio.run(_test())

def test_websocket_broadcast_agent_log():
    async def _test():
        manager = ConnectionManager()
        mock_ws1 = MagicMock()
        mock_ws1.accept = AsyncMock()
        mock_ws1.send_text = AsyncMock()

        mock_ws2 = MagicMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_text = AsyncMock()

        await manager.connect("proj_456", mock_ws1)
        await manager.connect("proj_456", mock_ws2)

        event_type = "AGENT_LOG"
        payload = {"agent": "ReviewerAgent", "message": "Code review approved."}
        await manager.broadcast("proj_456", event_type, payload)

        assert mock_ws1.send_text.call_count == 1
        assert mock_ws2.send_text.call_count == 1
    asyncio.run(_test())

def test_websocket_broadcast_human_interrupt():
    async def _test():
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await manager.connect("proj_789", mock_ws)
        interrupt_payload = {
            "approval_id": 1,
            "type": "clarifying_questions",
            "section": "Requirements Approval",
            "message": "Please verify the API parameters."
        }
        await manager.broadcast("proj_789", "HUMAN_INTERRUPT", interrupt_payload)
        mock_ws.send_text.assert_awaited_once()
    asyncio.run(_test())
