from utils.redis_utils import initialize_redis, REDIS_CHANNEL_MAPPING
from utils.logger import get_logger
import asyncio
from fastapi import FastAPI
from utils.websocket_utils import connection_manager
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
import json
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dev-negar-ai.leamech.com",  # Add your domain
        "http://localhost:3000",             # For local development
        "http://localhost:5004",
        "https://negar.leamech.com",
        "https://localhost:5005",
        ],  # Adjust this in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger = get_logger("mapping-service")

class UUIDConnectionManager:
    def __init__(self):
        self.active_connections = {}  # Dict of uuid -> list of connections
        
    async def connect(self, websocket: WebSocket, uuid: str):
        await websocket.accept()
        if uuid not in self.active_connections:
            self.active_connections[uuid] = []
        self.active_connections[uuid].append(websocket)
        return len(self.active_connections[uuid]) - 1  # Return connection index
        
    def disconnect(self, uuid: str, index: int):
        if uuid in self.active_connections:
            if 0 <= index < len(self.active_connections[uuid]):
                self.active_connections[uuid].pop(index)
            if not self.active_connections[uuid]:  # Remove uuid if no connections left
                del self.active_connections[uuid]
                
    async def send_personal_message(self, message: dict, uuid: str):
        if uuid in self.active_connections:
            for connection in self.active_connections[uuid]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to UUID {uuid}: {e}")
                    
    def get_connection_stats(self):
        return {
            "total_uuids": len(self.active_connections),
            "connections_per_uuid": {uuid: len(connections) for uuid, connections in self.active_connections.items()}
        }

uuid_manager = UUIDConnectionManager()

async def ai_mapping_listener():
    """Mapping service to map the AI results to the correct camera and UUID"""
    logger.info("Starting AI mapping service")
    
    x , z = 0, 0
    person_id = 0
           
    while True:
        redis_client = None
        pubsub = None
        
        try:
            redis_client = await initialize_redis()
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL_MAPPING)
            logger.info(f"Subscribed to {REDIS_CHANNEL_MAPPING} channel")

            while True:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True)
                    if message and message["type"] == "message":
                        try:
                            data = json.loads(message['data'].decode('utf-8'))
                            logger.info(f"Received message from {REDIS_CHANNEL_MAPPING} channel")
                            
                            if data["type"] != "ai_result":
                                logger.warning(f"Skipping non-AI result message: {data.get('type')}")
                                continue
                            
                            try:
                                # Extract UUID from the data if present
                                uuid = data["uuid"]
                                result = data["detections"]["results"]
                            except Exception as e:
                                logger.error(f"Error extracting UUID or results: {e}")
                                continue
                            
                            for person_id, cameras in result.items():
                                for camera_id, coordinates in cameras.items():
                                    x, z = coordinates[0]
                                    person_id = person_id
                            
                        
                            data = {
                                "data": {
                                    "persons": [    
                                        {
                                            "id": person_id,
                                            "bones": [],
                                            "joints": [],
                                            "location": {
                                                "x": x,
                                                "z": z
                                            },
                                            "isFallen": False,
                                            "isWalking": False,
                                            "direction": {
                                                "x": 0,
                                                "z": 0
                                            },
                                            "height": 180,
                                            "warning": False,
                                            "color": "0xffffff"
                                        }
                                    ],
                                    "congestions": [],
                                    "wet_floors": []
                                },
                                "uuid": uuid
                            }
                            logger.info(f"Broadcasting mapping data {data} to UUID: {uuid}")
                            if uuid and uuid in uuid_manager.active_connections:
                                logger.info(f"Broadcasting mapping data to UUID: {uuid}")
                                await uuid_manager.send_personal_message(data, uuid)
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON in message: {e}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)
                            
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"Error in message loop: {e}")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error in Redis connection: {e}")
            await asyncio.sleep(5)
            
        finally:
            try:
                await pubsub.unsubscribe(REDIS_CHANNEL_MAPPING)
                await pubsub.close()
                await redis_client.close()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")


@app.websocket("/ws/dt/")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for mapping service with required UUID"""
    uuid = None
    connection_index = None
    
    try:
        # Get UUID from query parameters
        uuid = websocket.query_params.get("uuid")
        if not uuid:
            logger.error("WebSocket connection attempted without UUID")
            return
            
        logger.info(f"WebSocket connection request with UUID: {uuid}")
        connection_index = await uuid_manager.connect(websocket, uuid)
        
        try:
            while True:
                try:
                    # Keep the connection alive and handle client messages
                    data = await websocket.receive_json()
                    # Handle any client messages here
                    await uuid_manager.send_personal_message({
                        "type": "ack",
                        "received": data,
                        "uuid": uuid,
                        "timestamp": datetime.now().isoformat()
                    }, uuid)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error handling message from UUID {uuid}: {e}")
        finally:
            if uuid and connection_index is not None:
                uuid_manager.disconnect(uuid, connection_index)
                logger.info(f"Client with UUID {uuid} disconnected")
                
    except Exception as e:
        logger.error(f"Error in websocket connection: {e}")
        if uuid and connection_index is not None:
            uuid_manager.disconnect(uuid, connection_index)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        redis_client = await initialize_redis()
        redis_ok = await redis_client.ping()
        await redis_client.close()
        
        connection_stats = uuid_manager.get_connection_stats()
        
        return {
            "status": "healthy",
            "redis_connected": redis_ok,
            "websocket_stats": connection_stats,
            "server_time": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "error_type": e.__class__.__name__,
            "timestamp": datetime.now().isoformat()
        }
    
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ai_mapping_listener())
    logger.info("Started AI mapping service")
    
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AI mapping service")
    
    

if __name__=="__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5005, reload=True)
