from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.websocket_manager import ws_manager

router = APIRouter(tags=["WebSockets"])

@router.websocket("/ws/projects/{project_id}")
@router.websocket("/ws/{project_id}")
async def project_events_websocket(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for subscribing to live orchestration events for a project."""
    await ws_manager.connect(project_id, websocket)
    try:
        while True:
            # Keep connection alive & accept incoming ping/pong or messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(project_id, websocket)
    except Exception:
        ws_manager.disconnect(project_id, websocket)
