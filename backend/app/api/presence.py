from fastapi import APIRouter, WebSocket

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def presence(socket: WebSocket, session_id: int):
    await socket.app.state.presence.connect(socket, session_id)
