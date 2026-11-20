import asyncio
from collections import deque
import json
import logging
from typing import Deque, Dict, List
from fastapi import WebSocket

logger = logging.getLogger("websocket_manager")

_BUFFER_MAX_EVENTS = 15


class ConnectionManager:
    def __init__(self):
        # Maps project_id -> list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Small recent-event ring buffer per project to eliminate early-event race on initial connect
        self._recent_events: Dict[str, Deque[str]] = {}

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        had_connections = bool(self.active_connections.get(project_id))
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.info(f"WebSocket connected for project_id: {project_id}")

        # Replay buffered events that arrived before the first client subscribed
        if not had_connections and project_id in self._recent_events:
            buffered = list(self._recent_events[project_id])
            self._recent_events[project_id].clear()
            for msg in buffered:
                try:
                    await websocket.send_text(msg)
                except Exception as e:
                    logger.warning(f"Failed to replay buffered WS message: {e}")
                    break

    def disconnect(self, project_id: str, websocket: WebSocket):
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.info(f"WebSocket disconnected for project_id: {project_id}")

    async def broadcast(self, project_id: str, event_type: str, data: dict):
        """Broadcast JSON payload concurrently to all WebSocket connections subscribed to project_id."""
        payload = {
            "event": event_type,
            "data": data
        }
        json_msg = json.dumps(payload, default=str)

        conns = list(self.active_connections.get(project_id, []))
        if not conns:
            # Buffer early events (excluding PONG) until a client connects
            if event_type != "PONG":
                buf = self._recent_events.setdefault(project_id, deque(maxlen=_BUFFER_MAX_EVENTS))
                buf.append(json_msg)
            return

        async def _send_one(conn: WebSocket):
            try:
                await asyncio.wait_for(conn.send_text(json_msg), timeout=5.0)
                return None
            except Exception as e:
                logger.warning(f"Failed to send WS message: {e}")
                return conn

        results = await asyncio.gather(*(_send_one(c) for c in conns), return_exceptions=False)
        for dead in results:
            if dead is not None:
                self.disconnect(project_id, dead)

    def broadcast_sync(self, project_id: str, event_type: str, data: dict):
        """Synchronous helper for background tasks and sub-threads to schedule a WS broadcast."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.broadcast(project_id, event_type, data))
                return
        except RuntimeError:
            pass

        main_loop = getattr(self, "main_loop", None)
        if main_loop and not main_loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(
                    self.broadcast(project_id, event_type, data),
                    main_loop,
                )
            except Exception as e:
                logger.warning(f"broadcast_sync failed for project {project_id} ({event_type}): {e}")
        else:
            logger.debug(f"broadcast_sync dropped {event_type} for project {project_id}: no active event loop")


ws_manager = ConnectionManager()
