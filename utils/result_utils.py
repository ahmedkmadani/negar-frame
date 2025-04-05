import logging
import time
from datetime import datetime
import json
import numpy as np
from utils.frame_utils import timestamp_from_frame

logger = logging.getLogger(__name__)

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

def format_result_data(filename, bucket, processed_filename, processed_bucket, 
                      original_url, processed_url, processing_time, people_data, camera_id, persons_info, result_type, uuid):
    """Format the result data for publishing to Redis"""
    
    data = {
        "type": result_type,
        "original_filename": filename,
        "original_bucket": bucket,
        "processed_filename": processed_filename,
        "processed_bucket": processed_bucket,
        "original_url": original_url,
        "processed_url": processed_url,
        "status": "success",
        "processing_time": processing_time,
        "timestamp": timestamp_from_frame(original_url),
        "camera_id": camera_id,
        "url": processed_url,
        "detections": {
            "total_persons": len(people_data),
            "people": people_data,
            "results": persons_info
        },
        "uuid": uuid
    }
        
    return data

def format_error_data(filename, error, **kwargs):
    """Format error data for publishing to Redis"""
    data = {
        "filename": filename if filename else "unknown",
        "status": "error",
        "error": str(error),
        "timestamp": datetime.now().isoformat()
    }
    # Add any additional kwargs
    data.update(kwargs)
    return data

async def publish_result(redis_client, channel, data):
    """Publish result to Redis channel"""
    try:
        await redis_client.publish(channel, str(data))
        logger.info(f"Published result to {channel}")
        return True
    except Exception as e:
        logger.error(f"Error publishing to {channel}: {e}")
        return False 