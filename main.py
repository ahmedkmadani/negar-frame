import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from flask_socketio.namespace import Namespace
from flask import request
import redis
from PIL import Image
import io
import threading
from datetime import datetime
from minio import Minio
import os
from base64 import b64encode
import logging
import time
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'asmkmkkasmd37483748jnjnfandfjdhw8uewfhjwnfjwfwuihfwuehfwuh'  # Required for Socket.IO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    async_mode='eventlet',
    message_queue=None,
    always_connect=True
)

# MinIO configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")  # Use the Docker service name
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "negar-dev")  # Use the root credentials from docker-compose
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "negar-dev")  # Use the root credentials from docker-compose
MINIO_BUCKET = "frames"

logger.info(f"Connecting to MinIO at {MINIO_ENDPOINT}")

# Initialize MinIO client
try:
    minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False  # Set to True if using HTTPS
    )
    logger.info(f"MinIO client initialized successfully: {minio_client}")
    logger.info(f"MinIO client initialized successfully: {minio_client.bucket_exists(MINIO_BUCKET)}")
    logger.info(f"MinIO access key: {MINIO_ACCESS_KEY}")
    logger.info(f"MinIO endpoint: {MINIO_ENDPOINT}")
    logger.info(f"MinIO secret key: {MINIO_SECRET_KEY}")
    logger.info("MinIO client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize MinIO client: {e}")
    raise

# Create bucket if it doesn't exist
try:
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)
        logger.info(f"Created new bucket: {MINIO_BUCKET}")
    else:
        logger.info(f"Bucket {MINIO_BUCKET} already exists")
except Exception as e:
    logger.error(f"Error checking/creating bucket: {e}")
    raise

# Redis connection pool configuration
REDIS_HOST = os.getenv('REDIS_HOST', '34.55.93.180')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

redis_pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    socket_timeout=10,
    socket_keepalive=True,
    socket_connect_timeout=10,
    retry_on_timeout=True,
    health_check_interval=30,
    max_connections=10
)


def get_connected_clients():
    try:
        if hasattr(socketio, 'server'):
            return len(socketio.server.eio.sockets)
        return 0
    except:
        return 0

def listen_to_channel():
    logger.info("Starting Redis listener thread")
    while True:  # Outer loop for reconnection
        try:
            # Connect to Redis with more robust configuration
            r = redis.Redis(connection_pool=redis_pool)
            
            # Test connection
            if not r.ping():
                logger.error("Could not ping Redis server")
                time.sleep(5)
                continue

            logger.info("Connected to Redis successfully")

            # Subscribe to the channel
            pubsub = r.pubsub()
            pubsub.subscribe('frame_sync')
            logger.info("Subscribed to 'frame_sync' channel")

            # Inner loop for message processing
            while True:
                try:
                    message = pubsub.get_message(timeout=1.0)
                    if message and message['type'] == 'message':
                        try:
                            # Decode the message
                            decoded_message = message['data'].decode('utf-8')
                            logger.info(f"Received message from Redis: {decoded_message[:100]}...")
                            
                            parts = decoded_message.split("--AKTAR--")
                            if len(parts) == 3:
                                timestamp = parts[0]
                                camera_list = parts[1].split(",")
                                logger.info(f"Processing frame for timestamp: {timestamp}, camera: {camera_list[0]}")
                                
                                image_data = r.hget(timestamp, camera_list[0])
                                
                                if image_data:
                                    logger.info(f"Retrieved image data from Redis, size: {len(image_data)} bytes")
                                    
                                    try:
                                        # Process image
                                        image = Image.open(io.BytesIO(image_data))
                                        logger.info(f"Image opened successfully: {image.format}, {image.size}")
                                        
                                        img_buffer = io.BytesIO()
                                        image.save(img_buffer, format='PNG')
                                        img_buffer.seek(0)
                                        
                                        filename = f"frame_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                                        
                                        # Upload to MinIO
                                        minio_client.put_object(
                                            MINIO_BUCKET,
                                            filename,
                                            img_buffer,
                                            img_buffer.getbuffer().nbytes,
                                            content_type='image/png'
                                        )
                                        logger.info(f"Uploaded to MinIO: {filename}")
                                        
                                        # Publish to AI channel
                                        try:
                                            r = redis.Redis(connection_pool=redis_pool)
                                            ai_message = {
                                                'bucket': MINIO_BUCKET,
                                                'filename': filename,
                                                'timestamp': timestamp,
                                                'camera_id': camera_list[0],
                                                'upload_time': datetime.now().isoformat()
                                            }
                                            r.publish('ai_channel', str(ai_message))
                                            logger.info(f"Published to AI channel: {filename}")
                                        except Exception as e:
                                            logger.error(f"Failed to publish to AI channel: {e}")
                                        
                                        # Prepare WebSocket data
                                        img_buffer.seek(0)
                                        base64_image = b64encode(img_buffer.read()).decode('utf-8')
                                        logger.info(f"Prepared base64 image data, length: {len(base64_image)}")
                                        
                                        # Check connected clients
                                        client_count = get_connected_clients()
                                        logger.info(f"Connected WebSocket clients: {client_count}")
                                        
                                        if client_count > 0:
                                            try:
                                                # Emit to all clients
                                                socketio.emit('new_frame', {
                                                    'image': base64_image,
                                                    'filename': filename,
                                                    'timestamp': datetime.now().isoformat()
                                                }, namespace='/', room=None)  # room=None broadcasts to all clients
                                                logger.info(f"Frame emitted via WebSocket: {filename}")
                                                socketio.sleep(0)
                                            except Exception as ws_error:
                                                logger.error(f"WebSocket emission error: {ws_error}", exc_info=True)
                                        else:
                                            logger.warning("No WebSocket clients connected, skipping emission")
                                    
                                    except Exception as e:
                                        logger.error(f"Error processing frame: {e}", exc_info=True)
                                else:
                                    logger.warning(f"No image data found in Redis for timestamp: {timestamp}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)
                            continue

                    # Small sleep to prevent CPU spinning
                    time.sleep(0.1)

                except redis.TimeoutError:
                    logger.warning("Redis operation timed out, checking connection...")
                    try:
                        if not r.ping():
                            logger.error("Lost connection to Redis")
                            break  # Break inner loop to reconnect
                    except:
                        logger.error("Could not ping Redis")
                        break  # Break inner loop to reconnect

                except redis.ConnectionError as e:
                    logger.error(f"Redis connection error: {e}")
                    break  # Break inner loop to reconnect

                except Exception as e:
                    logger.error(f"Unexpected error in message loop: {e}", exc_info=True)
                    time.sleep(1)

        except Exception as e:
            logger.error(f"Error establishing Redis connection: {e}", exc_info=True)
            time.sleep(5)  # Wait before retrying connection

        finally:
            try:
                pubsub.close()
            except:
                pass
            try:
                r.close()
            except:
                pass
            logger.info("Attempting to reconnect to Redis...")
            time.sleep(5)  # Wait before reconnecting

@socketio.on('connect')
def handle_connect():
    try:
        sid = request.sid
        logger.info(f"Client connected: {sid}")
        # Send a test frame to verify connection
        socketio.emit('test_connection', {
            'status': 'connected',
            'sid': sid,
            'timestamp': datetime.now().isoformat()
        }, room=sid)
        logger.info(f"Sent test connection message to {sid}")
    except Exception as e:
        logger.error(f"Error in connect handler: {e}", exc_info=True)

@socketio.on('disconnect')
def handle_disconnect():
    try:
        sid = request.sid
        logger.info(f"Client disconnected: {sid}")
    except Exception as e:
        logger.error(f"Error in disconnect handler: {e}", exc_info=True)

@socketio.on('ping')
def handle_ping():
    try:
        sid = request.sid
        logger.info(f"Received ping from client {sid}")
        socketio.emit('pong', {'timestamp': datetime.now().isoformat()}, room=sid)
    except Exception as e:
        logger.error(f"Error in ping handler: {e}", exc_info=True)

@socketio.on_error()
def error_handler(e):
    logger.error(f"SocketIO error: {str(e)}", exc_info=True)

@app.route('/')
def index():
    logger.info("Serving index page")
    return render_template('index.html')

@app.route('/history')
def history():
    logger.info("Serving history page")
    return render_template('history.html')

@app.route('/view_frame/<filename>')
def view_frame(filename):
    try:
        logger.info(f"Retrieving frame: {filename}")
        # Get the object data from MinIO
        data = minio_client.get_object(MINIO_BUCKET, filename).read()
        # Convert to base64
        base64_data = b64encode(data).decode('utf-8')
        return {
            'image': base64_data,
            'filename': filename
        }
    except Exception as e:
        logger.error(f"Error retrieving frame {filename}: {e}", exc_info=True)
        return {'error': str(e)}, 404

@app.route('/get_frames_history')
def get_frames_history():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        logger.info(f"Fetching frames history from MinIO (page {page}, {per_page} per page)")
        objects = list(minio_client.list_objects(MINIO_BUCKET))
        
        # Sort all objects by last_modified time before pagination
        objects.sort(key=lambda x: x.last_modified, reverse=True)  # Sort newest first
        
        # Calculate total pages and items
        total_items = len(objects)
        total_pages = (total_items + per_page - 1) // per_page
        
        # Get paginated subset of objects
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_objects = objects[start_idx:end_idx]
        
        # Format frame data
        frames = [{
            'name': obj.object_name,
            'last_modified': obj.last_modified.isoformat(),
            'timestamp': obj.object_name.replace('frame_', '').replace('.png', '').replace('_', ' ')
        } for obj in paginated_objects]
        
        logger.info(f"Found {total_items} total frames, returning page {page} of {total_pages}")
        return {
            'frames': frames,
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_items': total_items,
                'per_page': per_page
            }
        }
    except Exception as e:
        logger.error(f"Error getting frames history: {e}", exc_info=True)
        return {'frames': [], 'pagination': None}

@app.route('/health')
def health_check():
    try:
        # Check Redis connection using pool
        r = redis.Redis(connection_pool=redis_pool)
        redis_status = r.ping()
        
        # Check MinIO connection
        minio_status = minio_client.bucket_exists(MINIO_BUCKET)
        
        return {
            'status': 'healthy',
            'redis_connected': redis_status,
            'minio_connected': minio_status,
            'bucket_exists': minio_status,
            'redis_info': {
                'host': REDIS_HOST,
                'port': REDIS_PORT
            }
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e)
        }, 500

if __name__ == '__main__':
    # Start the Redis listener in a separate thread
    redis_thread = threading.Thread(target=listen_to_channel, daemon=True)
    redis_thread.start()
    logger.info("Redis listener thread started")
    
    # Run the Flask app with SocketIO
    logger.info("Starting Flask-SocketIO server")
    socketio.run(app, debug=True, host='0.0.0.0', port=5003)
