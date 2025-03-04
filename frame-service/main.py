import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime
import io
from PIL import Image
import base64

# Import our enhanced utility modules
from utils import (
    # Configuration
    WEBSOCKET_CONFIG,
    
    # Redis utilities
    initialize_redis,
    subscribe_to_channel,
    publish_message,
    get_message_with_timeout,
    safe_redis_operation,
    REDIS_CHANNEL_SYNC_FRAME,
    REDIS_CHANNEL_AI_RESULTS,
    
    # MinIO utilities
    get_object,
    put_object,
    get_presigned_url,
    list_objects,
    MINIO_BUCKET,
    ensure_bucket_exists,
    
    # WebSocket utilities
    ConnectionManager,
    
    # Frame utilities
    format_frame_message,
    format_ai_result_message,
    parse_message_data,
    process_frame_from_redis,
    process_aktar_frame,
    
    # Error handling utilities
    format_error,
    retry_async_operation,
    async_error_handler
)

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
    allow_origins=WEBSOCKET_CONFIG["cors_origins"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize connection manager
manager = ConnectionManager()

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
            
            # Process messages
            while True:
                try:
                    message = await get_message_with_timeout(pubsub, timeout=1.0)
                    
                    if message and message['type'] == 'message':
                        # Process the Aktar frame
                        frame_data = await process_aktar_frame(message['data'])
                        
                        if frame_data:
                            # Store in MinIO for persistence
                            filename = frame_data['filename']
                            image_data = frame_data['image_data']
                            timestamp = frame_data['timestamp']
                            camera_id = frame_data['camera_id']
                            
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
                                    'camera_id': camera_id,
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
                await redis_client.close()
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
                    
                    if message and message['type'] == 'message':
                        # Format the AI result message
                        result_message = format_ai_result_message(message['data'])
                        
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

@app.websocket("/ws/ai_results")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for clients to connect and receive AI results"""
    client_id = await manager.connect(websocket)
    
    try:
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
                await manager.disconnect(client_id)
                break
            except Exception as e:
                logger.error(f"Error processing client message: {e}")
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(client_id)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test Redis connection
        redis_client = await initialize_redis()
        redis_ok = await redis_client.ping()
        await redis_client.close()
        
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

@app.get("/api/latest-processed-images")
async def get_latest_processed_images(limit: int = 5):
    """Get the latest processed images from the AI results bucket"""
    try:
        # Get the AI results bucket name from config
        # This assumes the AI service is storing processed images in a specific bucket
        processed_bucket = "yolo-images"  # You might want to add this to your config
        
        # List objects in the bucket, sorted by last modified time (newest first)
        objects = list_objects(processed_bucket)
        
        # Sort objects by last modified time (newest first)
        sorted_objects = sorted(
            objects, 
            key=lambda obj: obj.last_modified, 
            reverse=True
        )[:limit]
        
        # Generate presigned URLs for each object
        results = []
        for obj in sorted_objects:
            # Generate a presigned URL
            url = get_presigned_url(processed_bucket, obj.object_name)
            
            # Extract timestamp and camera_id from filename if possible
            filename = obj.object_name
            metadata = {}
            
            # Try to parse metadata from filename (assuming format like camera_id_timestamp.jpg)
            try:
                parts = filename.split('_')
                if len(parts) >= 2:
                    camera_id = parts[0]
                    timestamp_str = '_'.join(parts[1:]).replace('.jpg', '')
                    
                    metadata = {
                        'camera_id': camera_id,
                        'timestamp': timestamp_str.replace('-', ':'),
                        'size': obj.size,
                        'last_modified': obj.last_modified.isoformat()
                    }
            except:
                # If parsing fails, just use basic metadata
                metadata = {
                    'size': obj.size,
                    'last_modified': obj.last_modified.isoformat()
                }
            
            results.append({
                'filename': filename,
                'url': url,
                'metadata': metadata
            })
        
        return {
            'status': 'success',
            'count': len(results),
            'images': results
        }
        
    except Exception as e:
        logger.error(f"Error getting latest processed images: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to retrieve latest processed images'
        }

@app.get("/images")
async def get_latest_frames(limit: int = 5):
    """Get the latest raw frames from the frames bucket"""
    try:
        # List objects in the frames bucket, sorted by last modified time (newest first)
        objects = list_objects(MINIO_BUCKET)
        
        # Sort objects by last modified time (newest first)
        sorted_objects = sorted(
            objects, 
            key=lambda obj: obj.last_modified, 
            reverse=True
        )[:limit]
        
        # Generate presigned URLs for each object
        results = []
        for obj in sorted_objects:
            # Generate a presigned URL
            url = get_presigned_url(MINIO_BUCKET, obj.object_name)
            
            # Extract timestamp and camera_id from filename if possible
            filename = obj.object_name
            metadata = {}
            
            # Try to parse metadata from filename (assuming format like camera_id_timestamp.jpg)
            try:
                parts = filename.split('_')
                if len(parts) >= 2:
                    camera_id = parts[0]
                    timestamp_str = '_'.join(parts[1:]).replace('.jpg', '')
                    
                    metadata = {
                        'camera_id': camera_id,
                        'timestamp': timestamp_str.replace('-', ':'),
                        'size': obj.size,
                        'last_modified': obj.last_modified.isoformat()
                    }
            except:
                # If parsing fails, just use basic metadata
                metadata = {
                    'size': obj.size,
                    'last_modified': obj.last_modified.isoformat()
                }
            
            results.append({
                'filename': filename,
                'url': url,
                'metadata': metadata
            })
        
        return {
            'status': 'success',
            'count': len(results),
            'images': results
        }
        
    except Exception as e:
        logger.error(f"Error getting latest frames: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to retrieve latest frames'
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5004, reload=True)
