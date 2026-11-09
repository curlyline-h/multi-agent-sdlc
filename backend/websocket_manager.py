import json
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("websocket_manager")

class ConnectionManager:
    def __init__(self):
        # Maps project_id -> list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.info(f"WebSocket connected for project_id: {project_id}")

    def disconnect(self, project_id: str, websocket: WebSocket):
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.info(f"WebSocket disconnected for project_id: {project_id}")

    async def broadcast(self, project_id: str, event_type: str, data: dict):
        """Broadcast JSON payload to all WebSocket connections subscribed to project_id."""
        if project_id not in self.active_connections:
            return

        payload = {
            "event": event_type,
            "data": data
        }
        json_msg = json.dumps(payload, default=str)

        disconnected = []
        for connection in self.active_connections[project_id]:
            try:
                await connection.send_text(json_msg)
            except Exception as e:
                logger.warning(f"Failed to send WS message: {e}")
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(project_id, conn)

    def broadcast_sync(self, project_id: str, event_type: str, data: dict):
        """Synchronous helper for background tasks and sub-threads to schedule a WS broadcast."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.broadcast(project_id, event_type, data))
        except RuntimeError:
            if hasattr(self, 'main_loop') and self.main_loop:
                asyncio.run_coroutine_threadsafe(self.broadcast(project_id, event_type, data), self.main_loop)

ws_manager = ConnectionManager()
