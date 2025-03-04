import logging
import traceback
from datetime import datetime
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

def format_error(error, context=None):
    """Format an error for logging and response"""
    error_data = {
        "error": str(error),
        "type": error.__class__.__name__,
        "timestamp": datetime.now().isoformat()
    }
    
    if context:
        error_data["context"] = context
        
    return error_data

async def retry_async_operation(operation, max_retries=3, retry_delay=5, *args, **kwargs):
    """Retry an async operation with exponential backoff"""
    retries = 0
    last_exception = None
    
    while retries < max_retries:
        try:
            return await operation(*args, **kwargs)
        except Exception as e:
            last_exception = e
            wait_time = retry_delay * (2 ** retries)
            logger.warning(f"Operation failed: {str(e)}. Retrying in {wait_time}s ({retries+1}/{max_retries})")
            await asyncio.sleep(wait_time)
            retries += 1
    
    logger.error(f"Operation failed after {max_retries} retries: {str(last_exception)}")
    raise last_exception

def async_error_handler(func):
    """Decorator to handle errors in async functions"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            logger.debug(traceback.format_exc())
            return None
    return wrapper 