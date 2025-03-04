import logging
from minio import Minio
from datetime import timedelta
import io
from typing import Union, Optional
from .config import MINIO_CONFIG
from .error_utils import async_error_handler

logger = logging.getLogger(__name__)

# Extract configuration
MINIO_ENDPOINT = MINIO_CONFIG["endpoint"]
MINIO_ACCESS_KEY = MINIO_CONFIG["access_key"]
MINIO_SECRET_KEY = MINIO_CONFIG["secret_key"]
MINIO_SECURE = MINIO_CONFIG["secure"]
MINIO_BUCKET = MINIO_CONFIG["bucket"]

# Initialize MinIO client
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

def get_object(bucket_name, object_name):
    """Get an object from MinIO"""
    try:
        response = minio_client.get_object(bucket_name, object_name)
        return response.read()
    except Exception as e:
        logger.error(f"Error getting object {object_name} from bucket {bucket_name}: {e}")
        return None

def put_object(bucket_name: str, object_name: str, data: Union[bytes, io.BytesIO], 
               content_length: Optional[int] = None, content_type: str = "application/octet-stream"):
    """Upload an object to MinIO"""
    try:
        # Convert bytes to BytesIO if needed
        if isinstance(data, bytes):
            data_io = io.BytesIO(data)
            length = len(data) if content_length is None else content_length
        else:
            data_io = data
            length = data.getbuffer().nbytes if content_length is None else content_length
        
        # Upload to MinIO
        result = minio_client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data_io,
            length=length,
            content_type=content_type
        )
        
        logger.info(f"Uploaded {object_name} to bucket {bucket_name}")
        return result
    except Exception as e:
        logger.error(f"Error uploading {object_name} to bucket {bucket_name}: {e}")
        return None

def get_presigned_url(bucket_name, object_name, expires=3600):
    """Generate a presigned URL for an object"""
    try:
        url = minio_client.presigned_get_object(
            bucket_name=bucket_name,
            object_name=object_name,
            expires=timedelta(seconds=expires)
        )
        return url
    except Exception as e:
        logger.error(f"Error generating presigned URL for {object_name}: {e}")
        return f"https://{MINIO_ENDPOINT}/{bucket_name}/{object_name}"

def list_objects(bucket_name, prefix="", recursive=True):
    """List objects in a bucket"""
    try:
        objects = minio_client.list_objects(
            bucket_name,
            prefix=prefix,
            recursive=recursive
        )
        return list(objects)
    except Exception as e:
        logger.error(f"Error listing objects in bucket {bucket_name}: {e}")
        return []

def ensure_bucket_exists(bucket_name):
    """Create bucket if it doesn't exist"""
    try:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            logger.info(f"Created bucket: {bucket_name}")
        return True
    except Exception as e:
        logger.error(f"Error ensuring bucket {bucket_name} exists: {e}")
        return False 