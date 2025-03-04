import os

# MinIO configuration
MINIO_CONFIG = {
    "endpoint": os.getenv("MINIO_ENDPOINT", "minio-dev.leamech.com"),
    "access_key": os.getenv("MINIO_ACCESS_KEY", "negar-dev"),
    "secret_key": os.getenv("MINIO_SECRET_KEY", "negar-dev"),
    "secure": os.getenv("MINIO_SECURE", "True").lower() == "true",
    "bucket": "frames"
}

# Redis configuration
REDIS_CONFIG = {
    "host": os.getenv('REDIS_HOST', '34.55.93.180'),
    "port": int(os.getenv('REDIS_PORT', 6379)),
    "db": int(os.getenv('REDIS_DB', 0)),
    "channels": {
        "sync_frame": "sync_frame",
        "ai_results": "ai_results"
    }
}

# WebSocket configuration
WEBSOCKET_CONFIG = {
    "cors_origins": [
        "*",  # Allow all origins in development
        "http://localhost",
        "http://localhost:3000",
        "https://leamech.com"
    ],
    "ping_interval": 30,  # seconds
    "ping_timeout": 10    # seconds
} 