import logging
import base64
from datetime import datetime
import io
from typing import Dict, Optional, Any, Union
import json
from .error_utils import async_error_handler

logger = logging.getLogger(__name__)

def encode_frame_to_base64(frame_data):
    """Encode frame data to base64"""
    try:
        if isinstance(frame_data, bytes):
            return base64.b64encode(frame_data).decode('utf-8')
        return frame_data
    except Exception as e:
        logger.error(f"Error encoding frame to base64: {e}")
        return None

def format_frame_message(filename: str, frame_data, timestamp=None, metadata=None):
    """Format a frame message for broadcasting with enhanced metadata"""
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    encoded_frame = encode_frame_to_base64(frame_data)
    if not encoded_frame:
        logger.error("Failed to encode frame")
        return None
    
    message = {
        'type': 'new_frame',
        'filename': filename,
        'image': encoded_frame,
        'timestamp': timestamp
    }
    
    if metadata:
        message['metadata'] = metadata
        
    return message

def parse_message_data(data: Union[str, bytes, Dict]) -> Dict:
    """Parse message data from various formats to a dictionary"""
    try:
        if isinstance(data, dict):
            return data
        elif isinstance(data, str):
            return json.loads(data)
        elif isinstance(data, bytes):
            return json.loads(data.decode('utf-8'))
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")
    except json.JSONDecodeError:
        # Try with eval as fallback for string representation of dict
        try:
            import ast
            return ast.literal_eval(data) if isinstance(data, str) else ast.literal_eval(data.decode('utf-8'))
        except:
            logger.error(f"Failed to parse message data: {data[:100]}...")
            raise

def format_ai_result_message(result_data):
    """Format an AI result message for broadcasting"""
    try:
        if not isinstance(result_data, dict):
            result_data = parse_message_data(result_data)
        
        # Ensure we have a timestamp
        if 'timestamp' not in result_data:
            result_data['timestamp'] = datetime.now().isoformat()
            
        return {
            'type': 'ai_result',
            'data': result_data,
            'timestamp': result_data.get('timestamp')
        }
    except Exception as e:
        logger.error(f"Error formatting AI result message: {e}")
        return None

@async_error_handler
async def process_frame_from_redis(redis_client, timestamp, camera_id):
    """Process a frame from Redis hash"""
    try:
        # Get image data from Redis hash
        image_data = await redis_client.hget(timestamp, camera_id)
        
        if not image_data:
            logger.warning(f"No image data found for timestamp {timestamp}, camera {camera_id}")
            return None
            
        logger.info(f"Retrieved image data from Redis, size: {len(image_data)} bytes")
        return image_data
    except Exception as e:
        logger.error(f"Error processing frame from Redis: {e}")
        return None 

@async_error_handler
async def process_aktar_frame(message_data):
    """Process an Aktar frame message with the specific delimiter format"""
    try:
        # Decode the message
        if isinstance(message_data, bytes):
            decoded_message = message_data.decode('utf-8')
        else:
            decoded_message = str(message_data)
        
        # Split by the Aktar delimiter
        parts = decoded_message.split("--AKTAR--")
        
        if len(parts) < 2:
            logger.warning(f"Invalid Aktar frame format: {decoded_message[:50]}...")
            return None
        
        # Parse the metadata part (first part)
        try:
            metadata = parse_message_data(parts[0])
            
            # Extract required fields
            timestamp = metadata.get('timestamp')
            camera_id = metadata.get('camera_id')
            
            if not timestamp or not camera_id:
                logger.warning(f"Missing required fields in Aktar frame metadata: {metadata}")
                return None
                
            # The second part is the base64 encoded image
            image_data_base64 = parts[1].strip()
            
            # Decode the base64 image
            try:
                image_data = base64.b64decode(image_data_base64)
                
                # Generate a filename
                filename = f"{camera_id}_{timestamp.replace(':', '-').replace('.', '-')}.jpg"
                
                return {
                    'filename': filename,
                    'image_data': image_data,
                    'metadata': metadata,
                    'timestamp': timestamp,
                    'camera_id': camera_id
                }
            except Exception as e:
                logger.error(f"Error decoding base64 image: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing Aktar frame metadata: {e}")
            return None
            
    except Exception as e:
        logger.error(f"Error processing Aktar frame: {e}")
        return None 