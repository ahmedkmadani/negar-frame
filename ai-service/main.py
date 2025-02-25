import redis
import time
import logging
import os
from ultralytics import YOLO
from PIL import Image, ImageDraw
import io
from minio import Minio
import numpy as np
import cv2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add YOLOv8 model initialization with CPU device
MODEL_PATH = "yolov8n.pt"  # Use yolov8n (nano) for faster CPU inference
model = YOLO(MODEL_PATH).to('cpu')

# MinIO configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = "frames"
MINIO_BUCKET_PROCESSED = "yolo-images"

REDIS_HOST = os.getenv('REDIS_HOST', '34.55.93.180')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

# Initialize MinIO client
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

# Ensure both buckets exist
try:
    # Check/create original bucket
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)
        logger.info(f"Created new bucket: {MINIO_BUCKET}")
    else:
        logger.info(f"Bucket {MINIO_BUCKET} already exists")
        
    # Check/create processed images bucket
    if not minio_client.bucket_exists(MINIO_BUCKET_PROCESSED):
        minio_client.make_bucket(MINIO_BUCKET_PROCESSED)
        logger.info(f"Created new bucket: {MINIO_BUCKET_PROCESSED}")
    else:
        logger.info(f"Bucket {MINIO_BUCKET_PROCESSED} already exists")
except Exception as e:
    logger.error(f"Error checking/creating buckets: {e}")
    raise

def process_image(image_data):
    # Convert bytes to numpy array for YOLOv8
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Run YOLOv8 detection with pose estimation
    results = model(img)
    
    # Convert back to PIL Image for drawing
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    
    # Process each detection
    for result in results[0].boxes.data:
        x1, y1, x2, y2, conf, class_id = result
        if int(class_id) == 0:  # class 0 is person in COCO dataset
            # Draw rectangle
            draw.rectangle([x1, y1, x2, y2], outline='red', width=2)
            
            # Get keypoints if available
            if hasattr(results[0], 'keypoints'):
                keypoints = results[0].keypoints.data
                for kps in keypoints:
                    # Process each keypoint
                    for kp in kps:
                        x, y, conf = kp
                        if conf > 0.5:  # Only process keypoints with confidence > 0.5
                            # Draw keypoint
                            draw.ellipse([x-2, y-2, x+2, y+2], fill='blue')
                    
                    # Log keypoint data
                    logger.info("Person keypoints: ")
                    keypoint_names = [
                        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
                        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                        "left_wrist", "right_wrist", "left_hip", "right_hip",
                        "left_knee", "right_knee", "left_ankle", "right_ankle"
                    ]
                    
                    for i, kp in enumerate(kps):
                        x, y, conf = kp
                        if conf > 0.5:
                            logger.info(f"{keypoint_names[i]}: x={x:.2f}, y={y:.2f}, confidence={conf:.2f}")
    
    logger.info("Detection boxes: ", results[0].boxes.data)
    logger.info("Full results: ", results)
    
    # Convert back to bytes
    img_byte_arr = io.BytesIO()
    img_pil.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr

def main():
    logger.info("Starting AI Service")
    
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            socket_timeout=10,
            socket_keepalive=True,
            retry_on_timeout=True
        )
        pubsub = r.pubsub()
        pubsub.subscribe('ai_channel')
        logger.info("Successfully subscribed to ai_channel")
        
        while True:
            try:
                message = pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    data = eval(message['data'].decode('utf-8'))
                    logger.info(f"Received message from ai_channel: {data}")
                    
                    bucket = data['bucket']
                    filename = data['filename']
                    
                    try:
                        # Get image from MinIO
                        logger.info(f"Retrieving image from MinIO: {filename}")
                        image_data = minio_client.get_object(bucket, filename).read()
                        
                        # Process image with YOLOv8
                        logger.info("Processing image with YOLOv8")
                        start_time = time.time()
                        processed_image = process_image(image_data)
                        processing_time = time.time() - start_time
                        logger.info(f"YOLOv8 processing completed in {processing_time:.2f} seconds")
                        
                        # Upload processed image to the new bucket
                        processed_filename = f"processed_{filename}"
                        minio_client.put_object(
                            MINIO_BUCKET_PROCESSED,
                            processed_filename,
                            processed_image,
                            processed_image.getbuffer().nbytes,
                            content_type='image/png'
                        )
                        logger.info(f"Uploaded processed image to {MINIO_BUCKET_PROCESSED}: {processed_filename}")
                        
                        # Publish results back to Redis
                        result_data = {
                            'original_filename': filename,
                            'original_bucket': bucket,
                            'processed_filename': processed_filename,
                            'processed_bucket': MINIO_BUCKET_PROCESSED,
                            'status': 'success',
                            'processing_time': processing_time
                        }
                        r.publish('ai_results', str(result_data))
                        logger.info("Published results to ai_results channel")
                        
                    except Exception as e:
                        logger.error(f"Error processing image: {e}", exc_info=True)
                        # Publish error to Redis
                        error_data = {
                            'filename': filename,
                            'status': 'error',
                            'error': str(e)
                        }
                        r.publish('ai_results', str(error_data))
                
                time.sleep(0.1)  # Prevent CPU spinning
                
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                time.sleep(1)  # Wait before retrying
                
    except Exception as e:
        logger.error(f"Redis connection error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()