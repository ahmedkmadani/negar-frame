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
from datetime import datetime, timedelta
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add YOLOv8 model initialization with CPU device
MODEL_PATH = "yolov8n-pose.pt"  
model = YOLO(MODEL_PATH).to('cpu') # Use yolov8n (nano) for faster CPU inference

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


def process_image(image_data):

    logger.info("\n" + "="*50)
    logger.info(f"Processing image")
    logger.info("="*50 + "\n")
                
                # Decode image
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                # Run detection
    results = model(img)
                
    # Convert to PIL image for drawing
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
                
    # Initialize people_data list to store all detected persons
    people_data = []
    
    # Check if results contain detections
    if len(results) > 0 and hasattr(results[0], 'boxes') and len(results[0].boxes) > 0:
        # Filter persons with confidence > 0.5
        persons = [(i, box) for i, box in enumerate(results[0].boxes.data) 
                    if int(box[5]) == 0 and box[4] > 0.5]
        
        logger.info(f"Found {len(persons)} person(s) with confidence > 0.5\n")
        
        for person_idx, result in persons:
            x1, y1, x2, y2, conf, class_id = result
            logger.info(f"Person {person_idx + 1}")
            logger.info(f"Confidence: {conf:.2f}")
            logger.info(f"Bounding Box: ({x1:.1f}, {y1:.1f}) to ({x2:.1f}, {y2:.1f})\n")
            
            # Draw bounding box
            draw.rectangle([x1, y1, x2, y2], outline='red', width=2)
            
            # Check if keypoints are available
            if hasattr(results[0], 'keypoints') and results[0].keypoints is not None:
                keypoints = results[0].keypoints.data[person_idx]
                
                # Define joint groups
                joint_groups = {
                    "Head": ["nose", "left_eye", "right_eye", "left_ear", "right_ear"],
                    "Upper Body": ["left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"],
                    "Lower Body": ["left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"]
                }
                
                keypoint_names = [
                    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
                    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                    "left_wrist", "right_wrist", "left_hip", "right_hip",
                    "left_knee", "right_knee", "left_ankle", "right_ankle"
                ]
                
                # Log and draw keypoints
                for group_name, joints in joint_groups.items():
                    logger.info(f"{group_name}:")
                    for joint in joints:
                        try:
                            idx = keypoint_names.index(joint)
                            x, y, conf = keypoints[idx]
                            if conf > 0.5:
                                draw.ellipse([x-3, y-3, x+3, y+3], fill='blue')
                                logger.info(f"  {joint:12s}: ({x:6.1f}, {y:6.1f}) conf={conf:.2f}")
                        except Exception as e:
                            logger.error(f"Error processing joint {joint}: {str(e)}")
                    logger.info("")
            
            person_data = {
                'confidence': float(conf),
                'bounding_box': {
                    'x1': float(x1),
                    'y1': float(y1),
                    'x2': float(x2),
                    'y2': float(y2)
                },
                'keypoints': {}
            }
            
            # Add keypoints if available
            if hasattr(results[0], 'keypoints') and results[0].keypoints is not None:
                keypoints = results[0].keypoints.data[person_idx]
                keypoint_names = [
                    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
                    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                    "left_wrist", "right_wrist", "left_hip", "right_hip",
                    "left_knee", "right_knee", "left_ankle", "right_ankle"
                ]
                
                # Group keypoints
                person_data['keypoints'] = {
                    'head': {},
                    'upper_body': {},
                    'lower_body': {}
                }
                
                for idx, name in enumerate(keypoint_names):
                    x, y, conf = keypoints[idx]
                    if conf > 0.5:  # Only include high-confidence keypoints
                        point_data = {
                            'x': float(x),
                            'y': float(y),
                            'confidence': float(conf)
                        }
                        
                        # Assign to appropriate group
                        if name in ["nose", "left_eye", "right_eye", "left_ear", "right_ear"]:
                            person_data['keypoints']['head'][name] = point_data
                        elif name in ["left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"]:
                            person_data['keypoints']['upper_body'][name] = point_data
                        else:
                            person_data['keypoints']['lower_body'][name] = point_data
            
            people_data.append(person_data)
    
    # Convert back to bytes
    img_byte_arr = io.BytesIO()
    img_pil.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    # Return both the processed image and the results
    return img_byte_arr, results, people_data

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
                        processed_image, results, people_data = process_image(image_data)
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
                            'processing_time': processing_time,
                            'detections': {
                                'total_persons': len(people_data),
                                'people': people_data
                            }
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

def test_process_images():
    """Test function to process all images in yolo-images bucket"""
    logger.info("Starting test: Processing all images in yolo-images bucket")
    
    try:
        # Initialize Redis
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            socket_timeout=10,
            socket_keepalive=True,
            retry_on_timeout=True
        )
        
        # List all objects in yolo-images bucket
        objects = list(minio_client.list_objects(MINIO_BUCKET))
        total_images = len(objects)
        logger.info(f"Found {total_images} images to process")
        
        for idx, obj in enumerate(objects, 1):
            try:
                filename = obj.object_name
                logger.info(f"\nProcessing image {idx}/{total_images}: {filename}")
                
                # Get image data
                image_data = minio_client.get_object(MINIO_BUCKET, filename).read()
                
                # Process image
                start_time = time.time()
                processed_image, results, people_data = process_image(image_data)
                processing_time = time.time() - start_time
                
                # Upload processed image
                processed_filename = f"test_processed_{filename}"
                minio_client.put_object(
                    MINIO_BUCKET_PROCESSED,
                    processed_filename,
                    processed_image,
                    processed_image.getbuffer().nbytes,
                    content_type='image/png'
                )
                
                
                # Publish results
                result_data = {
                    'original_filename': filename,
                    'original_bucket': MINIO_BUCKET_PROCESSED,
                    'processed_filename': processed_filename,
                    'processed_bucket': MINIO_BUCKET_PROCESSED,
                    'status': 'success',
                    'processing_time': processing_time,
                    'detections': {
                        'total_persons': len(people_data),
                        'people': people_data
                    }
                }
                
                r.publish('ai_results', str(result_data))
                logger.info(f"Published results for {filename}")
                
                # Add delay between images
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}", exc_info=True)
                error_data = {
                    'test_id': f"test_{int(time.time())}",
                    'image_index': idx,
                    'total_images': total_images,
                    'filename': filename,
                    'status': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
                r.publish('ai_results', str(error_data))
                continue
        
        logger.info("\nTest completed: All images processed")
        
    except Exception as e:
        logger.error(f"Test function error: {e}", exc_info=True)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_process_images()
    else:
        main()

