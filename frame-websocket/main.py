import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
import json
import logging
import os
from typing import List, Dict
from datetime import datetime, timedelta
from minio import Minio
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Results WebSocket Service",
    description="WebSocket service for streaming AI detection results",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
class Settings:
    REDIS_HOST = os.getenv('REDIS_HOST', '34.55.93.180')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_CHANNEL = 'ai_results'
    RECONNECT_DELAY = 5  # seconds
    HEARTBEAT_INTERVAL = 30  # seconds

settings = Settings()

MINIO_BUCKET = "frames"
MINIO_BUCKET_PROCESSED = "yolo-images"
MINIO_BUCKET_PROCESSED_TEST = "yolo-images-test"

# Add MinIO configuration
class MinioSettings:
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio-dev.leamech.com")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "negar-dev")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "negar-dev")
    MINIO_BUCKET_PROCESSED = "yolo-images"
    MINIO_BUCKET_PROCESSED_TEST = "yolo-images-test"    
    MINIO_SECURE = True

minio_settings = MinioSettings()

minio_client = Minio(
    minio_settings.MINIO_ENDPOINT,
    access_key=minio_settings.MINIO_ACCESS_KEY,
    secret_key=minio_settings.MINIO_SECRET_KEY,
    secure=minio_settings.MINIO_SECURE
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_times: Dict[str, datetime] = {}

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        client_id = str(id(websocket))
        self.active_connections[client_id] = websocket
        self.connection_times[client_id] = datetime.now()
        await self.send_personal_message({
            "type": "connection_status",
            "status": "connected",
            "client_id": client_id,
            "connected_at": self.connection_times[client_id].isoformat(),
            "total_clients": len(self.active_connections)
        }, client_id)
        logger.info(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
        return client_id

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            del self.connection_times[client_id]
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
            await asyncio.sleep(settings.HEARTBEAT_INTERVAL)
            await self.broadcast({
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat(),
                "connected_clients": len(self.active_connections)
            })

manager = ConnectionManager()

async def redis_listener():
    """Background task to listen to Redis channel and broadcast messages"""
    while True:
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True
            )
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(settings.REDIS_CHANNEL)
            logger.info(f"Subscribed to {settings.REDIS_CHANNEL} channel")

            while True:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True)
                    if message and message['type'] == 'message':
                        try:
                            # Parse the message data
                            data = eval(message['data'])  # Using eval since the data is a string representation of dict
                            data['received_timestamp'] = datetime.now().isoformat()
                            
                            # Add metadata
                            data['metadata'] = {
                                'channel': settings.REDIS_CHANNEL,
                                'active_clients': len(manager.active_connections)
                            }
                            
                            logger.info(f"Broadcasting AI result to {len(manager.active_connections)} clients")
                            await manager.broadcast(data)
                            
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                    
                    await asyncio.sleep(0.1)  # Prevent CPU overload
                    
                except Exception as e:
                    logger.error(f"Error in message loop: {e}")
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Redis connection error: {e}")
            await asyncio.sleep(settings.RECONNECT_DELAY)

@app.on_event("startup")
async def startup_event():
    """Start background tasks when the application starts"""
    asyncio.create_task(redis_listener())
    asyncio.create_task(manager.send_heartbeat())
    logger.info("Started background tasks")

@app.websocket("/ws/ai_results")
async def websocket_endpoint(websocket: WebSocket):
    client_id = await manager.connect(websocket)
    try:
        while True:
            try:
                # Keep the connection alive and handle client messages
                data = await websocket.receive_json()
                # Handle any client messages here
                await manager.send_personal_message({
                    "type": "ack",
                    "received": data,
                    "timestamp": datetime.now().isoformat()
                }, client_id)
            except WebSocketDisconnect:
                manager.disconnect(client_id)
                break
            except Exception as e:
                logger.error(f"Error handling message from client {client_id}: {e}")
    finally:
        manager.disconnect(client_id)

@app.get("/images")
def get_images():
    try:
        # List objects in the bucket
        objects = list(minio_client.list_objects(
            minio_settings.MINIO_BUCKET_PROCESSED,
            recursive=True
        ))
        
        # Sort objects by last modified time (newest first)
        objects.sort(key=lambda obj: obj.last_modified, reverse=True)
        
        # Get the 5 most recent images
        recent_images = objects[:5]
        
        image_data = []
        for obj in recent_images:
            # Generate presigned URL (valid for 1 hour)
            url = minio_client.presigned_get_object(
                minio_settings.MINIO_BUCKET_PROCESSED,
                obj.object_name,
                expires=timedelta(hours=1)
            )
            
            image_data.append({
                "filename": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat(),
                "url": url
            })
        
        return {
            "status": "success",
            "count": len(image_data),
            "images": image_data
        }
    
    except Exception as e:
        logger.error(f"Error retrieving images: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True
        )
        await redis_client.ping()
        
        # Get connection statistics
        current_time = datetime.now()
        connection_stats = {
            client_id: {
                "connected_for": str(current_time - connected_at),
                "connected_at": connected_at.isoformat()
            }
            for client_id, connected_at in manager.connection_times.items()
        }
        
        return {
            "status": "healthy",
            "redis_connected": True,
            "websocket_clients": {
                "total": len(manager.active_connections),
                "connections": connection_stats
            },
            "server_time": current_time.isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
