import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from routes.webscoet_ai import websocket_route
from routes.frame_ai import frame_ai_route
from utils.logger import get_logger
from utils.websocket_utils import ConnectionManager
from utils.config import WEBSOCKET_CONFIG
from utils.redis_utils import initialize_redis, subscribe_to_channel, publish_message, get_message_with_timeout, REDIS_CHANNEL_SYNC_FRAME, REDIS_CHANNEL_AI_RESULTS
from utils.minio_utils import put_object, MINIO_BUCKET, ensure_bucket_exists
from utils.frame_utils import process_aktar_frame, format_ai_result_message
from utils.error_utils import async_error_handler
from PIL import Image
import io

app = FastAPI(
    title="AI Results WebSocket & API Service",
    description="""
    WebSocket & API service for streaming AI detection results.
    
    Features:
    - Real-time AI detection results via WebSocket
    - REST API for retrieving processed images
    - MinIO integration for image storage
    """,
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_version="3.1.0"  # Added OpenAPI version
)

logger = get_logger("frame-service")

# Initialize connection manager
manager = ConnectionManager()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
          "https://dev-negar-ai.leamech.com",  # Add your domain
        "http://localhost:3000",             # For local development
        "http://localhost:5004", 
        ],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



async def frame_listener():
    """Background task to listen for new frames from Redis"""
    logger.info("Starting frame listener task")
    
    while True:  # Outer loop for reconnection
        redis_client = None
        pubsub = None
        
        try:
            # Initialize Redis
            redis_client = await initialize_redis()
            
            # Test connection
            if not await redis_client.ping():
                logger.error("Could not ping Redis server")
                await asyncio.sleep(5)
                continue

            logger.info("Connected to Redis successfully")

            # Subscribe to frame_sync channel
            pubsub = await subscribe_to_channel(redis_client, REDIS_CHANNEL_SYNC_FRAME)
            logger.info(f"Subscribed to {REDIS_CHANNEL_SYNC_FRAME} channel")
            
            await pubsub.subscribe('frame_sync')
            logger.info("Subscribed to 'frame_sync' channel")   
            message = await pubsub.get_message(timeout=1.0)

            # Process messages
            while True:
                try:
                    message = await get_message_with_timeout(pubsub, timeout=1.0)
                    logger.info(f"Received message: {message}")
                    
                    if message and message['type'] == 'message':
                        # Process the Aktar frame
                        decoded_message = message['data'].decode('utf-8')
                        parts = decoded_message.split("--AKTAR--")
                        if len(parts) == 3:
                            timestamp = parts[0]
                            camera_list = parts[1].split(",")
                            logger.info(f"Processing frame for timestamp: {timestamp}, camera: {camera_list[0]}")
                            
                            image_data = await redis_client.hget(timestamp, camera_list[0])
                            
                            if image_data:
                                logger.info(f"Retrieved image data from Redis, size: {len(image_data)} bytes")
                                    # Process image
                                image = Image.open(io.BytesIO(image_data))
                                logger.info(f"Image opened successfully: {image.format}, {image.size}")
                                
                                img_buffer = io.BytesIO()
                                image.save(img_buffer, format='PNG')
                                img_buffer.seek(0)
                                
                                filename = f"frame_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                            
                            # Upload to MinIO
                            put_object(
                                MINIO_BUCKET, 
                                filename, 
                                image_data, 
                                content_type="image/jpeg"
                            )
                            
                            # Publish to AI channel
                            try:
                                ai_message = {
                                    'bucket': MINIO_BUCKET,
                                    'filename': filename,
                                    'timestamp': timestamp,
                                    'camera_id': camera_list[0],
                                    'upload_time': datetime.now().isoformat()
                                }
                                await publish_message(redis_client, 'ai_channel', str(ai_message))
                                logger.info(f"Published to AI channel: {filename}")
                            except Exception as e:
                                logger.error(f"Failed to publish to AI channel: {e}")
                
                    # Small delay to prevent CPU spinning
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"Error in frame listener loop: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Error in frame listener: {e}")
        
        # Clean up connections
        if pubsub:
            try:
                await pubsub.close()
            except:
                pass
                
        if redis_client:
            try:
                redis_client.close()
            except:
                pass
        
        # Wait before reconnecting
        logger.info("Attempting to reconnect to Redis in 5 seconds...")
        await asyncio.sleep(5)

async def ai_result_listener():
    """Background task to listen for AI results from Redis"""
    logger.info("Starting AI results listener task")
    
    while True:  # Outer loop for reconnection
        redis_client = None
        pubsub = None
        
        try:
            # Initialize Redis
            redis_client = await initialize_redis()
            
            # Subscribe to AI results channel
            pubsub = await subscribe_to_channel(redis_client, REDIS_CHANNEL_AI_RESULTS)
            logger.info(f"Subscribed to {REDIS_CHANNEL_AI_RESULTS} channel")
            
            # Process messages
            while True:
                try:
                    message = await get_message_with_timeout(pubsub, timeout=1.0)
                    logger.info(f"Subscribed to {REDIS_CHANNEL_AI_RESULTS} channel")

                    logger.info(f"Received message: {message}")
                    if message and message['type'] == 'message':
                        # Format the AI result message
                        result_message = await format_ai_result_message(message['data'])
                        
                        if result_message:
                            # Broadcast to all connected clients
                            await manager.broadcast(result_message)
                            logger.info(f"Broadcasted AI result: {result_message.get('data', {}).get('processed_filename', 'unknown')}")
                    
                    # Small delay to prevent CPU spinning
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"Error in AI results listener loop: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Error in AI results listener: {e}")
        
        # Clean up connections
        if pubsub:
            try:
                await pubsub.close()
            except:
                pass
                
        if redis_client:
            try:
                await redis_client.close()
            except:
                pass
        
        # Wait before reconnecting
        logger.info("Attempting to reconnect to Redis in 5 seconds...")
        await asyncio.sleep(5)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test Redis connection
        redis_client = await initialize_redis()
        redis_ok = await redis_client.ping()
        redis_client.close()
        
        # Get connection statistics
        connection_stats = manager.get_connection_stats()
        
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
    """Start background tasks on application startup"""
    # Ensure bucket exists
    ensure_bucket_exists(MINIO_BUCKET)
    
    # Start background tasks
    asyncio.create_task(ai_result_listener())
    asyncio.create_task(frame_listener())
    
    # Start heartbeat task
    asyncio.create_task(manager.start_heartbeat(WEBSOCKET_CONFIG["ping_interval"]))
    
    logger.info("Background tasks started")

app.include_router(websocket_route)
app.include_router(frame_ai_route)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5004, reload=True)
