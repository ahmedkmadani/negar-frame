import logging
import json
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Callable, Any
import asyncio
from .error_utils import async_error_handler



logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30

class ConnectionManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConnectionManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if not ConnectionManager._initialized:
            self.active_connections: Dict[str, WebSocket] = {}
            self._connection_counter = 0
            ConnectionManager._initialized = True
            logger.info("ConnectionManager initialized")

    async def connect(self, websocket: WebSocket) -> str:
        """Register a new WebSocket connection"""
        await websocket.accept()
        self._connection_counter += 1
        client_id = str(self._connection_counter)
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
        return client_id

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: Dict, client_id: str):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to client {client_id}: {e}")
                await self.disconnect(client_id)

    async def broadcast(self, message: Dict):
        disconnected_clients = []
        for client_id, connection in self.active_connections.items():
            try:
                await connection.send_json({
                    **message,
                    "broadcast_time": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)

    async def send_heartbeat(self):
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await self.broadcast({
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat(),
                "connected_clients": len(self.active_connections)
            })
            
    def get_connection_stats(self):
        return {
            "total_clients": len(self.active_connections),
        }
        
    

# Create a single instance to be imported by other modules
connection_manager = ConnectionManager()
        
    
