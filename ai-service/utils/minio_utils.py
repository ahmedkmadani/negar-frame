import logging
from minio import Minio
from datetime import timedelta
import json
from .config import MINIO_CONFIG

logger = logging.getLogger(__name__)

# Extract configuration
MINIO_ENDPOINT = MINIO_CONFIG["endpoint"]
MINIO_ACCESS_KEY = MINIO_CONFIG["access_key"]
MINIO_SECRET_KEY = MINIO_CONFIG["secret_key"]
MINIO_SECURE = MINIO_CONFIG["secure"]
MINIO_BUCKET = MINIO_CONFIG["buckets"]["frames"]
MINIO_BUCKET_PROCESSED = MINIO_CONFIG["buckets"]["processed"]
MINIO_BUCKET_PROCESSED_TEST = MINIO_CONFIG["buckets"]["processed_test"]

# Initialize MinIO client
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

def ensure_bucket_exists(bucket_name):
    """Create bucket if it doesn't exist and set public read access"""
    try:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            logger.info(f"Created bucket: {bucket_name}")
        
        # Set public read policy
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                }
            ]
        }
        minio_client.set_bucket_policy(bucket_name, json.dumps(policy))
        logger.info(f"Set public read policy for bucket: {bucket_name}")
    except Exception as e:
        logger.error(f"Error setting up bucket {bucket_name}: {e}")

def get_minio_url(bucket, filename):
    """Generate a URL for a MinIO object"""
    try:
        url = minio_client.presigned_get_object(
            bucket_name=bucket,
            object_name=filename,
            expires=timedelta(hours=1)
        )
        return url
    except Exception as e:
        return f"https://{MINIO_ENDPOINT}/{bucket}/{filename}" 