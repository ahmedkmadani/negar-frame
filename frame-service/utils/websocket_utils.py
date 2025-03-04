import logging
import json
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Callable, Any
import asyncio
from .error_utils import async_error_handler

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Enhanced WebSocket connection manager"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_times: Dict[str, datetime] = {}
        self.connection_metadata: Dict[str, Dict] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        
    async def connect(self, websocket: WebSocket, metadata: Optional[Dict] = None) -> str:
        """Connect a new client with optional metadata"""
        await websocket.accept()
        client_id = str(id(websocket))
        self.active_connections[client_id] = websocket
        self.connection_times[client_id] = datetime.now()
        
        if metadata:
            self.connection_metadata[client_id] = metadata
        else:
            self.connection_metadata[client_id] = {}
            
        # Trigger connect event
        await self._trigger_event('connect', client_id, websocket)
        
        logger.info(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
        return client_id
    
    async def disconnect(self, client_id: str):
        """Disconnect a client by ID"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            
            # Trigger disconnect event
            await self._trigger_event('disconnect', client_id, websocket)
            
            del self.active_connections[client_id]
            del self.connection_times[client_id]
            
            if client_id in self.connection_metadata:
                del self.connection_metadata[client_id]
                
            logger.info(f"Client {client_id} disconnected. Total connections: {len(self.active_connections)}")
    
    @async_error_handler
    async def send_personal_message(self, message: Dict, client_id: str):
        """Send a message to a specific client by ID"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            
            # Add metadata
            if not message.get('timestamp'):
                message['timestamp'] = datetime.now().isoformat()
                
            await websocket.send_json(message)
            return True
        return False
    
    @async_error_handler
    async def broadcast(self, message: Dict, exclude: Optional[List[str]] = None):
        """Broadcast a message to all connected clients with optional exclusions"""
        if not self.active_connections:
            logger.debug("No clients connected, skipping broadcast")
            return 0
            
        # Add timestamp if not present
        if not message.get('timestamp'):
            message['timestamp'] = datetime.now().isoformat()
            
        # Add metadata
        message['metadata'] = {
            'broadcast_time': datetime.now().isoformat(),
            'active_clients': len(self.active_connections)
        }
        
        exclude_set = set(exclude or [])
        disconnected_clients = []
        sent_count = 0
        
        for client_id, websocket in self.active_connections.items():
            if client_id in exclude_set:
                continue
                
            try:
                await websocket.send_json(message)
                sent_count += 1
            except WebSocketDisconnect:
                disconnected_clients.append(client_id)
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {e}")
                disconnected_clients.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)
        
        return sent_count
    
    async def broadcast_to_group(self, message: Dict, group_filter: Callable[[str, Dict], bool]):
        """Broadcast a message to a filtered group of clients"""
        if not self.active_connections:
            return 0
            
        target_clients = [
            client_id for client_id in self.active_connections
            if group_filter(client_id, self.connection_metadata.get(client_id, {}))
        ]
        
        sent_count = 0
        for client_id in target_clients:
            if await self.send_personal_message(message, client_id):
                sent_count += 1
                
        return sent_count
    
    async def broadcast_frame(self, filename: str, image_data, timestamp=None, metadata=None):
        """Broadcast a frame to all connected clients"""
        from .frame_utils import format_frame_message
        
        message = format_frame_message(filename, image_data, timestamp, metadata)
        if message:
            clients_count = await self.broadcast(message)
            logger.info(f"Broadcasted frame {filename} to {clients_count} clients")
            return clients_count
        return 0
    
    def register_event_handler(self, event: str, handler: Callable):
        """Register a handler for connection events"""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        self.event_handlers[event].append(handler)
    
    async def _trigger_event(self, event: str, client_id: str, websocket: WebSocket):
        """Trigger handlers for an event"""
        if event in self.event_handlers:
            for handler in self.event_handlers[event]:
                try:
                    await handler(client_id, websocket, self.connection_metadata.get(client_id, {}))
                except Exception as e:
                    logger.error(f"Error in {event} event handler: {e}")
    
    async def start_heartbeat(self, interval: int = 30):
        """Start sending heartbeat messages to all clients"""
        while True:
            await asyncio.sleep(interval)
            if self.active_connections:
                await self.broadcast({
                    'type': 'heartbeat',
                    'timestamp': datetime.now().isoformat(),
                    'connected_clients': len(self.active_connections)
                })
                logger.debug(f"Sent heartbeat to {len(self.active_connections)} clients")
    
    def get_connection_stats(self):
        """Get statistics about current connections"""
        current_time = datetime.now()
        return {
            'total': len(self.active_connections),
            'connections': {
                client_id: {
                    'connected_for': str(current_time - self.connection_times[client_id]),
                    'connected_at': self.connection_times[client_id].isoformat(),
                    'metadata': self.connection_metadata.get(client_id, {})
                }
                for client_id in self.active_connections
            }
        } 