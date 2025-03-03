import logging
import redis.asyncio as redis
import json
from .config import REDIS_CONFIG
from .error_utils import retry_async_operation, async_error_handler

logger = logging.getLogger(__name__)

# Extract configuration
REDIS_HOST = REDIS_CONFIG["host"]
REDIS_PORT = REDIS_CONFIG["port"]
REDIS_DB = REDIS_CONFIG["db"]
REDIS_CHANNEL_SYNC_FRAME = REDIS_CONFIG["channels"]["sync_frame"]
REDIS_CHANNEL_AI_RESULTS = REDIS_CONFIG["channels"]["ai_results"]

# Redis connection pool
_redis_pool = None

async def get_redis_pool():
    """Get or create Redis connection pool"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
        logger.info(f"Created Redis connection pool to {REDIS_HOST}:{REDIS_PORT}")
    return _redis_pool

async def initialize_redis():
    """Initialize Redis connection from pool"""
    try:
        pool = await get_redis_pool()
        r = redis.Redis(connection_pool=pool)
        # Test connection
        if await r.ping():
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            return r
        else:
            logger.error("Failed to ping Redis server")
            raise ConnectionError("Could not ping Redis server")
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