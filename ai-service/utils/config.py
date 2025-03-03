import os

# MinIO configuration
MINIO_CONFIG = {
    "endpoint": os.getenv("MINIO_ENDPOINT", "minio-dev.leamech.com"),
    "access_key": os.getenv("MINIO_ACCESS_KEY", "negar-dev"),
    "secret_key": os.getenv("MINIO_SECRET_KEY", "negar-dev"),
    "secure": os.getenv("MINIO_SECURE", "True").lower() == "true",
    "buckets": {
        "frames": "frames",
        "processed": "yolo-images",
        "processed_test": "yolo-images-test"
    }
}

# Redis configuration
REDIS_CONFIG = {
    "host": os.getenv('REDIS_HOST', '34.55.93.180'),
    "port": int(os.getenv('REDIS_PORT', 6379)),
    "db": int(os.getenv('REDIS_DB', 0)),
    "channels": {
        "input": "ai_channel",
        "output": "ai_results"
    }
}

# Model configuration
MODEL_CONFIG = {
    "path": os.getenv("MODEL_PATH", "yolov8n-pose.pt"),
    "device": os.getenv("MODEL_DEVICE", "cpu"),
    "confidence_threshold": float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
} 