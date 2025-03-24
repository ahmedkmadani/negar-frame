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

async def ai_mapping_listener():
    """Mapping service to map the AI results to the correct camera"""
    logger.info("Starting AI mapping service")
           
    while True:  # Outer loop for reconnection
        redis_client = None
        pubsub = None
        
        try:
            # Initialize Redis
            redis_client = await initialize_redis()
            pubsub = redis_client.pubsub()
            
            # Subscribe to channel
            await pubsub.subscribe(REDIS_CHANNEL_MAPPING)
            logger.info(f"Subscribed to {REDIS_CHANNEL_MAPPING} channel")

            while True:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True)
                    if message and message["type"] == "message":
                        try:
                            # Parse JSON message data
                            print("--------------------------------")
                            print("data in ai_mapping_listener", message["data"])
                            print("--------------------------------")
                            data = json.loads(message['data'].decode('utf-8'))
                            logger.info(f"Received message from {REDIS_CHANNEL_MAPPING} channel")
                            
                            if data["type"] != "ai_result":
                                logger.warning(f"Skipping non-AI result message: {data.get('type')}")
                                continue
                            
                            status = data["status"]
                            total_persons = data["detections"]["total_persons"]
                            results = data["detections"]["results"]
                            camera_id = data["camera_id"]
                            people = data["detections"]["people"]
                            
                            data = {
                                "status": status,
                                "total_persons": total_persons,
                                "results": results,
                                "camera_id": camera_id,
                                "people": people
                            }

                            logger.info(f"Broadcasting mapping data to {len(connection_manager.active_connections)} clients")
                            await connection_manager.broadcast(data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON in message: {e}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)
                            
                    await asyncio.sleep(0.01)  # Prevent CPU spinning
                    
                except Exception as e:
                    logger.error(f"Error in message loop: {e}")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error in Redis connection: {e}")
            await asyncio.sleep(5)  # Wait before reconnecting
            
        finally:
            # Cleanup
            try:
                await pubsub.unsubscribe(REDIS_CHANNEL_MAPPING)
                await pubsub.close()
                await redis_client.close()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")


@app.websocket("/ws/mapping")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for mapping service"""
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
        

    
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test Redis connection
        redis_client = await initialize_redis()
        redis_ok = await redis_client.ping()
        redis_client.close()
        
        # Get connection statistics
        connection_stats = connection_manager.get_connection_stats()
        
        return {
            "status": "healthy",
            "redis_connected": redis_ok,
            "websocket_clients": connection_stats,
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
