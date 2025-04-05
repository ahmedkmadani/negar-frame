from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from utils.minio_utils import list_objects, get_presigned_url
from utils.logger import get_logger
from utils.config import MINIO_CONFIG
from utils.frame_utils import timestamp_from_frame

MINIO_BUCKET = MINIO_CONFIG["buckets"]["frames"]
MINIO_BUCKET_PROCESSED = MINIO_CONFIG["buckets"]["processed"]

logger = get_logger("frame-service")

frame_ai_route = APIRouter(tags=["Frame AI"], prefix="/api")

from datetime import datetime

class ImageMetadata(BaseModel):
    camera_id: Optional[str] = Field(None, example="camera_01")
    timestamp: Optional[str] = Field(None, example="2024-03-10T12:30:45")
    size: int = Field(..., example=1024576)
    last_modified: str = Field(..., example="2024-03-10T12:30:45.123Z")


class ImageInfo(BaseModel):
    filename: str = Field(..., example="camera_01_2024-03-10-12-30-45.jpg")
    url: str = Field(..., example="https://example.com/image.jpg")
    metadata: ImageMetadata


class ImageInfoResponse(BaseModel):
    images: List[ImageInfo] = Field(default_factory=list)

@frame_ai_route.get(
    "/frame/history/")
async def get_latest_processed_images(
    limit: int = Query(
        default=5,
        description="Number of images to return",
        ge=1,
        le=50
    )
):
    """
    Get the latest processed images from the AI results bucket
    
    - **limit**: Number of images to return (default: 5, max: 50)
    """
    try:
        # Get the AI results bucket name from config
        # This assumes the AI service is storing processed images in a specific bucket
        processed_bucket = MINIO_BUCKET_PROCESSED
        
        # List objects in the bucket, sorted by last modified time (newest first)
        objects = list_objects(processed_bucket)
        
        # Sort objects by last modified time (newest first)
        sorted_objects = sorted(
            objects, 
            key=lambda obj: obj.last_modified, 
            reverse=True
        )[:limit]
        
        # Generate presigned URLs for each object
        frames = []
        for obj in sorted_objects:
            # Generate a presigned URL
            url = get_presigned_url(processed_bucket, obj.object_name)
            
            # Extract timestamp from filename
            filename = obj.object_name
            timestamp = timestamp_from_frame(url)

            frame = {
                'timestamp': timestamp,
                'frame': [
                    {
                        'camera_id': 0,
                        'url': url,
                    }
                ]
            }
            
            frames.append(frame)

        return frames
          
        
            

  
        
    except Exception as e:
        logger.error(f"Error getting latest processed images: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to retrieve latest processed images'
        }

@frame_ai_route.get(
    "/latest-frames",
    response_model=ImageInfoResponse)
async def get_latest_frames(
    limit: int = Query(
        default=5,
        description="Number of frames to return",
        ge=1,
        le=50
    )
):
    """
    Get the latest raw frames from the frames bucket
    
    - **limit**: Number of frames to return (default: 5, max: 50)
    """
    try:
        frames_bucket = MINIO_BUCKET
        # List objects in the frames bucket, sorted by last modified time (newest first)
        objects = list_objects(frames_bucket)
        
        # Sort objects by last modified time (newest first)
        sorted_objects = sorted(
            objects, 
            key=lambda obj: obj.last_modified, 
            reverse=True
        )[:limit]
        
        # Generate presigned URLs for each object
        results = []
        for obj in sorted_objects:
            # Generate a presigned URL
            url = get_presigned_url(frames_bucket, obj.object_name)
            
            # Extract timestamp and camera_id from filename if possible
            filename = obj.object_name
            metadata = {}
            
            # Try to parse metadata from filename (assuming format like camera_id_timestamp.jpg)
            try:
                parts = filename.split('_')
                if len(parts) >= 2:
                    camera_id = parts[0]
                    timestamp_str = '_'.join(parts[1:]).replace('.jpg', '')
                    
                    metadata = {
                        'camera_id': camera_id,
                        'timestamp': timestamp_str.replace('-', ':'),
                        'size': obj.size,
                        'last_modified': obj.last_modified.isoformat()
                    }
            except:
                # If parsing fails, just use basic metadata
                metadata = {
                    'size': obj.size,
                    'last_modified': obj.last_modified.isoformat()
                }
            
            results.append({
                'filename': filename,
                'url': url,
                'metadata': metadata
            })
        
        return {
            'status': 'success',
            'count': len(results),
            'images': results
        }
        
    except Exception as e:
        logger.error(f"Error getting latest frames: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to retrieve latest frames'
        }
