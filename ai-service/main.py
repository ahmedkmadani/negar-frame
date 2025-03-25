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
from test_process_images import test_process_images
from PIL import Image
from io import BytesIO

logger = get_logger("ai-service")

# Initialize YOLO model
model = initialize_model()

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


async def main():
    """Main function to process images from Redis queue"""
    logger.info("Starting AI service")
    
    with open("config.yaml", 'r') as f:
        cfg = yaml.safe_load(f)

    person_localizer = PersonLocalizer(cfg.get("localizing", {}))
    
    try:
        # Initialize Redis
        r = await initialize_redis()
        
        # Subscribe to the frames channel
        pubsub = r.pubsub()
        await pubsub.subscribe(REDIS_CHANNEL_AI_CHANNEL)
        logger.info(f"Subscribed to {REDIS_CHANNEL_AI_CHANNEL} channel")
        
        while True:
            try:
                message = await pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    data = eval(message['data'].decode('utf-8'))
                    logger.info(f"Received message from ai_channel: {data}")
                    
                    bucket = data['bucket']
                    filename = data['filename']
                    
                    # Verify bucket exists
                    if not minio_client.bucket_exists(bucket):
                        logger.error(f"Bucket {bucket} does not exist")
                        continue
                    
                    try:
                        # Check if object exists before trying to get it
                        try:
                            minio_client.stat_object(bucket, filename)
                        except Exception as e:
                            logger.error(f"Object {filename} not found in bucket {bucket}: {e}")
                            # Wait a short time and retry once
                            await asyncio.sleep(0.5)
                            try:
                                minio_client.stat_object(bucket, filename)
                            except:
                                continue
                        
                        # Get image from MinIO
                        logger.info(f"Retrieving image from MinIO: {filename}")
                        image_data = minio_client.get_object(bucket, filename).read()
                        
                        # Process image with YOLOv8
                        logger.info("Processing image with YOLOv8")
                        start_time = time.time()
                        processed_image, results, people_data = process_image(image_data, model)
                        processing_time = time.time() - start_time
                        logger.info(f"YOLOv8 processing completed in {processing_time:.2f} seconds")
                        
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
                        
                        
                        # Upload processed image to the new bucket
                        processed_filename = f"processed_{filename.rsplit('.', 1)[0]}.jpg"
                        original_url = get_presigned_url(bucket, filename)
                        processed_url = get_presigned_url(MINIO_BUCKET_PROCESSED, processed_filename)
                        camera_id = ["camera1"]
                    
                        detections = yolov8pose_post_process(results)
                        persons_info = person_localizer(camera_id, detections)
                        
                        
                        # Ensure processed bucket exists
                        ensure_bucket_exists(MINIO_BUCKET_PROCESSED)
                        
                        minio_client.put_object(
                            MINIO_BUCKET_PROCESSED,
                            processed_filename,
                            compressed_image,
                            compressed_image.getbuffer().nbytes,
                            content_type='image/jpeg'
                        )
                        logger.info(f"Uploaded processed image to {MINIO_BUCKET_PROCESSED}: {processed_filename}")
                        
                        # Publish results back to Redis
                        result_data = format_result_data(
                            filename, MINIO_BUCKET, processed_filename, MINIO_BUCKET_PROCESSED,
                            original_url, processed_url, processing_time, people_data, camera_id, persons_info, "ai_result"
                        )
                        
                        await r.publish(REDIS_CHANNEL_AI_RESULTS, json.dumps(result_data, cls=NumpyEncoder))
                
                        await r.publish(REDIS_CHANNEL_MAPPING, json.dumps(result_data, cls=NumpyEncoder))
                        logger.info(f"Published results to {REDIS_CHANNEL_MAPPING} channel and {REDIS_CHANNEL_AI_RESULTS} channel")
                        
                    except Exception as e:
                        logger.error(f"Error processing image: {e}", exc_info=True)
                        # Publish error
                        error_data = {
                            'status': 'error',
                            'filename': filename,
                            'bucket': bucket,
                            'error': str(e),
                            'timestamp': data.get('timestamp'),
                            'camera_id': data.get('camera_id')
                        }
                        await r.publish(REDIS_CHANNEL_AI_RESULTS, str(error_data))
                
                await asyncio.sleep(0.1)  # Prevent CPU spinning
                
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                await asyncio.sleep(1)  # Wait before retrying
                
    except Exception as e:
        logger.error(f"Redis connection error: {e}", exc_info=True)
        raise



if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_process_images())
    else:
        asyncio.run(main())
        # asyncio.run(test_process_images())


