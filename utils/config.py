import os

# MinIO configuration
MINIO_CONFIG = {
    "endpoint": os.getenv("MINIO_ENDPOINT", ""),
    "access_key": os.getenv("MINIO_ACCESS_KEY", ""),
    "secret_key": os.getenv("MINIO_SECRET_KEY", ""),
    "secure": os.getenv("MINIO_SECURE", "True").lower() == "true",
    "buckets": {
        "frames": "frames",
        "processed": "yolo-images",
        "processed_test": "yolo-images-test"
    }
}

# Redis configuration
REDIS_CONFIG = {
    "host": os.getenv('REDIS_HOST'),
    "port": int(os.getenv('REDIS_PORT', 6379)),
    "db": int(os.getenv('REDIS_DB', 0)),
    "password": os.getenv('REDIS_PASSWORD', ''),
    "channels": {
        "ai_channel": "ai_channel",
        "sync_frame": "sync_frame",
        "ai_results": "ai_results",
        "mapping": "ai_mapping"
    }
}

# Model configuration
MODEL_CONFIG = {
    "model_name": os.getenv("MODEL_NAME", "yolov8l-pose"),
    "device": os.getenv("MODEL_DEVICE", "cpu"),
    "confidence_threshold": float(os.getenv("CONFIDENCE_THRESHOLD", "0.05"))
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