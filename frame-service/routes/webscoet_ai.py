from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter
from datetime import datetime
from utils.websocket_utils import ConnectionManager
from utils.logger import get_logger
# Import our enhanced utility modules
from utils.frame_utils import (
    parse_message_data
)

logger = get_logger("frame-service")

# Initialize connection manager
manager = ConnectionManager()

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
    client_id = None
    try:
        # Accept the WebSocket connection first
        await websocket.accept()
        logger.info("WebSocket connection accepted")

        # Then connect to the manager
        client_id = await manager.connect(websocket)
        logger.info(f"Client {client_id} registered with manager")
        
        # Send welcome message
        await manager.send_personal_message({
            "type": "connection_established",
            "client_id": client_id,
            "message": "Connected to AI Results WebSocket",
            "timestamp": datetime.now().isoformat()
        }, client_id)
        
        # Handle client messages
        while True:
            try:
                data = await websocket.receive_text()
                message = parse_message_data(data)
                
                # Handle ping messages
                if message.get("type") == "ping":
                    await manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }, client_id)
                
            except WebSocketDisconnect:
                logger.info(f"Client {client_id} disconnected")
                break
            except Exception as e:
                logger.error(f"Error processing client message: {e}")
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if client_id:
            await manager.disconnect(client_id)
            logger.info(f"Client {client_id} cleanup completed")
