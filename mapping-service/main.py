from math import floor
from utils.redis_utils import initialize_redis, REDIS_CHANNEL_MAPPING, REDIS_CHANNEL_HEATMAP
from utils.logger import get_logger
import asyncio
from fastapi import FastAPI
from utils.websocket_utils import connection_manager
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
import json
from fastapi.middleware.cors import CORSMiddleware
from utils.mongodb_utils import MONGO_HEATMAP_COLLECTION, MONGO_HEATMAP_HISTORY_COLLECTION, mongo_client
from utils.config import MONGO_CONFIG


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dev-negar-ai.leamech.com",  # Add your domain
        "http://localhost:3000",             # For local development
        "http://localhost:5004",
        "https://negar.leamech.com",
        "https://localhost:5005",
        "https://dev-negar.leamech.com",
        ],  # Adjust this in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger = get_logger("mapping-service")

username = "lahroodi"

db_name = MONGO_CONFIG["db"]

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
                                detections = data["detections"]
                                result = data["detections"]["results"]
                                
                                # Extract location data and prepare persons array
                                persons_array = []
                                points_array = []
                                for person_id, cameras in result.items():
                                    for camera_id, coordinates in cameras.items():
                                        # Get the coordinates
                                        x, z = coordinates[0]
                                        
                                        person = {
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
                                        space_width = 100
                                        space_length = 100
                                        
                                        points_array.append({'point': {'x': floor(x/space_width), 'z':floor(z/space_length)}, "value": 5})
                                        persons_array.append(person)
                                        break  # Only use first camera for now
                                
                                logger.info(f"Created persons array with {len(persons_array)} entries")
                            except Exception as e:
                                logger.error(f"Error creating persons array: {e}")
                                persons_array = []
                                points_array = []
                                
                            # Only proceed if persons were detected
                            if persons_array:
                                data = {
                                    "data": {
                                        "persons": persons_array,
                                        "congestions": [],
                                        "wet_floors": []
                                    },
                                    "uuid": uuid
                                }
                                
                                logger.info(f"Broadcasting mapping data to UUID: {uuid}")
                                if uuid and uuid in uuid_manager.active_connections:
                                    logger.info(f"Broadcasting mapping data with {len(persons_array)} persons to UUID: {uuid}")
                                    await uuid_manager.send_personal_message(data, uuid)
                                    
                                    # Send heatmap data to redis channel
                                    #TODO: change the time to the timestamp of the frame
                                    logger.info(f"Sending heatmap data to {REDIS_CHANNEL_HEATMAP} channel")
                                    try:
                                        # Add debug log before preparing heatmap data
                                        logger.info("Preparing heatmap data")
                                        text_data_json = {"heatmap": 
                                            {'points':
                                                points_array, 
                                            "time":datetime.now().isoformat(), 
                                            'person_current_count':len(persons_array)}}
                                        
                                        # Add debug log for heatmap data content
                                        logger.info(f"Prepared heatmap data: {text_data_json}")
                                        
                                        heatmap_data = {'ft':text_data_json["heatmap"], 'username': username}
                                        logger.info(f"Publishing to {REDIS_CHANNEL_HEATMAP}: {heatmap_data}")
                                        await redis_client.publish(REDIS_CHANNEL_HEATMAP, json.dumps(heatmap_data))
                                        logger.info(f"Successfully published heatmap data to {REDIS_CHANNEL_HEATMAP}")
                                    except Exception as e:
                                        logger.error(f"Error in heatmap processing/publishing: {e}", exc_info=True)
                                    
                                    try:
                                        collection = username + MONGO_HEATMAP_COLLECTION
                                        # Using db_name variable to access the database
                                        db = mongo_client[db_name]
                                        db[collection].insert_one(text_data_json)
                                        logger.info(f"Written heatmap data to {collection} collection in database {db_name}")
                                    except Exception as e:
                                        logger.error(f"Error in writing heatmap data to MongoDB: {e}", exc_info=True)
                                    
                                    try:
                                        collection_heatmap_history = username + MONGO_HEATMAP_HISTORY_COLLECTION
                                        # Check if point exists and add new coordinates to existing ones, or create new point
                                        for item in points_array:
                                            x_point = item["point"]["x"]
                                            z_point = item["point"]["z"]
                                            value = item["value"]
                                            
                                            db = mongo_client[db_name]
                                            # First try to find if the point exists
                                            existing_point = db[collection_heatmap_history].find_one({"x": x_point, "z": z_point})
                                        
                                            if existing_point:
                                            # If point exists, add new x and z to existing values
                                                db[collection_heatmap_history].update_one({"x": x_point, "z": z_point, "value": existing_point["value"] + 5})
                                            else:
                                                # If point doesn't exist, create new document
                                                db[collection_heatmap_history].insert_one({"x": x_point, "z": z_point, "value": value})
                                                logger.info(f"Updated heatmap history data in {collection_heatmap_history} collection")
                                    except Exception as e:
                                        logger.error(f"Error in updating heatmap history data in MongoDB: {e}", exc_info=True)
                                    
                            else:
                                logger.info(f"No persons detected, skipping broadcast for UUID: {uuid}")
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
