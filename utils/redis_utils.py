import logging
from .config import REDIS_CONFIG
from urllib.parse import quote_plus
from .error_utils import retry_async_operation, async_error_handler
import json
from redis.asyncio import Redis
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Extract configuration
REDIS_HOST = REDIS_CONFIG["host"]
REDIS_PORT = REDIS_CONFIG["port"]
REDIS_DB = REDIS_CONFIG["db"]
REDIS_CHANNEL_INPUT = REDIS_CONFIG["channels"]["input"]
REDIS_CHANNEL_OUTPUT = REDIS_CONFIG["channels"]["output"]
REDIS_PASSWORD = REDIS_CONFIG["password"]
REDIS_CHANNEL_SYNC_FRAME = REDIS_CONFIG["channels"]["sync_frame"]
REDIS_CHANNEL_AI_RESULTS = REDIS_CONFIG["channels"]["ai_results"]

async def initialize_redis():
    """Initialize Redis connection with retry and keepalive settings"""
    try:
        is_domain = '.' in REDIS_HOST and not REDIS_HOST.startswith('.')
        if is_domain:
            # URL encode the password to handle special characters
            encoded_password = quote_plus(REDIS_PASSWORD)
            redis_url = f"redis://:{encoded_password}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
            r = Redis.from_url(redis_url,
                            socket_timeout=10,
                            socket_keepalive=True,
                            socket_connect_timeout=5,
                            retry_on_timeout=True,
                            health_check_interval=15)
        else:
            r = Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                socket_timeout=10,
                socket_keepalive=True,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                health_check_interval=15,
                decode_responses=True
            )
        # Test connection
        await r.ping()
        logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return r
    except Exception as e:
        logger.error(f"Redis connection error: {e}", exc_info=True)
        raise 
    
@async_error_handler
async def subscribe_to_channel(redis_client, channel):
    """Subscribe to a Redis channel with error handling"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    logger.info(f"Subscribed to channel: {channel}")
    return pubsub

@async_error_handler
async def publish_message(redis_client, channel, message):
    """Publish a message to a Redis channel with error handling"""
    if isinstance(message, dict):
        message = json.dumps(message)
    result = await redis_client.publish(channel, message)
    logger.info(f"Published message to channel: {channel}")
    return result

@async_error_handler
async def get_message_with_timeout(pubsub, timeout=1.0):
    """Get a message from a pubsub channel with timeout"""
    return await pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)

async def safe_redis_operation(operation, *args, **kwargs):
    """Execute a Redis operation with retry logic"""
    return await retry_async_operation(operation, *args, **kwargs) 