import json
import time
from datetime import datetime
from utils.logger import get_logger
import asyncio
# Import our utility modules
from utils import (
    process_image,
    ensure_bucket_exists,
    get_presigned_url,
    minio_client,
    MINIO_BUCKET,
    MINIO_BUCKET_PROCESSED,
    MINIO_BUCKET_PROCESSED_TEST,
    initialize_redis,
    initialize_model,
    format_result_data,
    format_error_data,
    REDIS_CHANNEL_MAPPING,
    REDIS_CHANNEL_AI_CHANNEL,
    REDIS_CHANNEL_AI_RESULTS
)
import numpy as np
import yaml
from localizing import PersonLocalizer
from utils.redis_utils import REDIS_CHANNEL_AI_RESULTS
from utils.result_utils import NumpyEncoder
from PIL import Image
from io import BytesIO

logger = get_logger("ai-service")

model = initialize_model()

uuid = "2d2ae9ad-3b56-4de3-be2c-31560511e7ea"


# Ensure all required buckets exist
ensure_bucket_exists(MINIO_BUCKET)
ensure_bucket_exists(MINIO_BUCKET_PROCESSED)
ensure_bucket_exists(MINIO_BUCKET_PROCESSED_TEST)


def yolov8pose_post_process(detections, threshold=0.50):
    result = []
    for res in detections:
        bconfs = res.boxes.conf
        boxes = res.boxes.xyxy.reshape(-1, 4)[bconfs > threshold]
        boxes = boxes.cpu().numpy().astype("int32")
        keypoints = res.keypoints.xy.reshape(-1, 17, 2)[bconfs > threshold]
        keypoints = keypoints.cpu().numpy().astype("int32")
        
        # Fix the size check - use len() or check if array is empty
        if res.keypoints.conf is not None and len(res.keypoints.conf) > 0:
            confs = res.keypoints.conf[bconfs > threshold]
            confs = confs.cpu().numpy().reshape(-1, 17)
        else:
            confs = np.array([]).reshape(-1, 17)
            
        result.append({"boxes": boxes, "keypoints": keypoints, "confs": confs})
    return result

async def test_process_images():
    """Test function to process all images in frames bucket"""
    logger.info("Starting test: Processing all images in frames bucket")
    
    with open("config.yaml", 'r') as f:
        cfg = yaml.safe_load(f)

    person_localizer = PersonLocalizer(cfg.get("localizing", {}))
    
    try:
        # Initialize Redis
        r = await initialize_redis()
        
        # List all objects in frames bucket
        try:    
            objects = list(minio_client.list_objects(MINIO_BUCKET))
            total_images = len(objects)
            logger.info(f"Found {total_images} images to process")
        except Exception as e:
            logger.error(f"Error listing objects: {e}", exc_info=True)
            return
        
        for idx, obj in enumerate(objects, 1):
            try:
                filename = obj.object_name
                logger.info(f"\nProcessing image {idx}/{total_images}: {filename}")
                
                # Get image data
                image_data = minio_client.get_object(MINIO_BUCKET, filename).read()
                
                # Process image
                start_time = time.time()
                processed_image, results, people_data = process_image(image_data, model)
                processing_time = time.time() - start_time
                
                # Get original size
                processed_image.seek(0)
                original_size = processed_image.getbuffer().nbytes / (1024 * 1024)  # Convert to MB
                logger.info(f"Original image size: {original_size:.2f} MB")
                
                # Compress the processed image using JPEG
                img = Image.open(processed_image)
                compressed_image = BytesIO()
                # Convert to RGB mode as JPEG doesn't support RGBA
                if img.mode in ('RGBA', 'LA'):
                    img = img.convert('RGB')
                img.save(compressed_image, format='JPEG', quality=120)
                compressed_image.seek(0)
                
                # Get compressed size
                compressed_size = compressed_image.getbuffer().nbytes / (1024 * 1024)  # Convert to MB
                logger.info(f"Compressed image size: {compressed_size:.2f} MB (reduced by {((original_size - compressed_size) / original_size * 100):.1f}%)")
                
                # Upload processed image
                processed_filename = f"test_processed_{filename.rsplit('.', 1)[0]}.jpg"
                original_url = get_presigned_url(MINIO_BUCKET, filename)
                processed_url = get_presigned_url(MINIO_BUCKET_PROCESSED_TEST, processed_filename)
                camera_id = ["camera1"]
                
                minio_client.put_object(
                    MINIO_BUCKET_PROCESSED_TEST,
                    processed_filename,
                    compressed_image,
                    compressed_image.getbuffer().nbytes,
                    content_type='image/jpeg'
                )
                
                logger.info(f"Original image: {original_url}")
                logger.info(f"Processed image: {processed_url}")
                
                detections = yolov8pose_post_process(results)
                persons_info = person_localizer(camera_id, detections)
                # Format and publish results
                result_data = format_result_data(
                    filename, MINIO_BUCKET, processed_filename, MINIO_BUCKET_PROCESSED_TEST,
                    original_url, processed_url, processing_time, people_data, camera_id, persons_info, "ai_result", uuid
                )
                await r.publish(REDIS_CHANNEL_AI_RESULTS, json.dumps(result_data, cls=NumpyEncoder))
                
                await r.publish(REDIS_CHANNEL_MAPPING, json.dumps(result_data, cls=NumpyEncoder))
                logger.info(f"Published results for {filename}")
                
                # Add delay between images
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}", exc_info=True)
                error_data = format_error_data(
                    filename, 
                    e,
                    test_id=f"test_{int(time.time())}",
                    image_index=idx,
                    total_images=total_images,
                    timestamp=datetime.now().isoformat()
                )
                await r.publish(REDIS_CHANNEL_AI_RESULTS, str(error_data))
                continue
        
        logger.info("\nTest completed: All images processed")
        
    except Exception as e:
        logger.error(f"Test function error: {e}", exc_info=True)