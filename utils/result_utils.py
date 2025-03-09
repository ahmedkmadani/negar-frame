import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

def format_result_data(filename, bucket, processed_filename, processed_bucket, 
                      original_url, processed_url, processing_time, people_data):
    """Format the result data for publishing to Redis"""
    return {
        'original_filename': filename,
        'original_bucket': bucket,
        'processed_filename': processed_filename,
        'processed_bucket': processed_bucket,
        'original_url': original_url,
        'processed_url': processed_url,
        'status': 'success',
        'processing_time': processing_time,
        'timestamp': datetime.now().isoformat(),
        'detections': {
            'total_persons': len(people_data),
            'people': people_data
        }
    }

def format_error_data(filename, error, **kwargs):
    """Format error data for publishing to Redis"""
    data = {
        'filename': filename if filename else 'unknown',
        'status': 'error',
        'error': str(error),
        'timestamp': datetime.now().isoformat()
    }
    # Add any additional kwargs
    data.update(kwargs)
    return data

def publish_result(redis_client, channel, data):
    """Publish result to Redis channel"""
    try:
        redis_client.publish(channel, str(data))
        logger.info(f"Published result to {channel}")
        return True
    except Exception as e:
        logger.error(f"Error publishing to {channel}: {e}")
        return False 