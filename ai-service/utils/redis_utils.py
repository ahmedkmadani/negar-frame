import logging
import redis
from .config import REDIS_CONFIG

logger = logging.getLogger(__name__)

# Extract configuration
REDIS_HOST = REDIS_CONFIG["host"]
REDIS_PORT = REDIS_CONFIG["port"]
REDIS_DB = REDIS_CONFIG["db"]
REDIS_CHANNEL_INPUT = REDIS_CONFIG["channels"]["input"]
REDIS_CHANNEL_OUTPUT = REDIS_CONFIG["channels"]["output"]

def initialize_redis():
    """Initialize Redis connection with retry and keepalive settings"""
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            socket_timeout=10,
            socket_keepalive=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=15
        )
        # Test connection
        r.ping()
        logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return r
    except Exception as e:
        logger.error(f"Redis connection error: {e}", exc_info=True)
        raise 