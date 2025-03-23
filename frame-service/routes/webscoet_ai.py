from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter
from datetime import datetime
from utils.websocket_utils import connection_manager
from utils.logger import get_logger
# Import our enhanced utility modules
from utils.frame_utils import (
    parse_message_data
)

logger = get_logger("frame-service")

# Initialize connection manager

# Add description for the WebSocket endpoints
websocket_route = APIRouter(
    tags=["WebSocket"],
    prefix="/ws",
    responses={
        200: {
            "description": "WebSocket connection established successfully"
        }
    }
)

@websocket_route.websocket("/ai_results", name="AI Results WebSocket")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time AI results.
    
    Connect to this WebSocket at: ws://{host}/ws/ai_results
    
    Messages:
    - Incoming ping: {"type": "ping"}
    - Outgoing pong: {"type": "pong", "timestamp": "ISO-8601 timestamp"}
    - Connection established: {
        "type": "connection_established",
        "client_id": "unique_id",
        "message": "Connected to AI Results WebSocket",
        "timestamp": "ISO-8601 timestamp"
    }
    """
    client_id = await connection_manager.connect(websocket)
    try:
        while True:
            try:
                # Keep the connection alive and handle client messages
                data = await websocket.receive_json()
                # Handle any client messages here
                await connection_manager.send_personal_message({
                    "type": "ack",
                    "received": data,
                    "timestamp": datetime.now().isoformat()
                }, client_id)
            except WebSocketDisconnect:
                connection_manager.disconnect(client_id)
                break
            except Exception as e:
                logger.error(f"Error handling message from client {client_id}: {e}")
    finally:
        connection_manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")