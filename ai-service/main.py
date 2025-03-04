import time
import logging
from datetime import datetime

# Import our utility modules
from utils import (
    process_image,
    ensure_bucket_exists,
    get_minio_url,
    minio_client,
    MINIO_BUCKET,
    MINIO_BUCKET_PROCESSED,
    MINIO_BUCKET_PROCESSED_TEST,
    initialize_redis,
    initialize_model,
    format_result_data,
    format_error_data,
    publish_result,
    REDIS_CHANNEL_INPUT,
    REDIS_CHANNEL_OUTPUT
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize YOLO model
model = initialize_model()

# Ensure all required buckets exist
ensure_bucket_exists(MINIO_BUCKET)
ensure_bucket_exists(MINIO_BUCKET_PROCESSED)
ensure_bucket_exists(MINIO_BUCKET_PROCESSED_TEST)

<<<<<<< HEAD
# Update the URL generation function
def get_minio_url(bucket, filename, expiry=timedelta(hours=1)):
    """Generate a URL for a MinIO object
    
    Args:
        bucket: The MinIO bucket name
        filename: The object name/path in the bucket
        expiry: Expiration time for presigned URLs (default: 1 hour)
    
    Returns:
        A URL to access the object - presigned if needed for non-public buckets
    """
    try:
        # Try to generate a presigned URL (works for both public and private buckets)
        url = minio_client.presigned_get_object(
            bucket_name=bucket,
            object_name=filename,
            expires=expiry.total_seconds()
        )
        return url
    except Exception as e:
        logger.warning(f"Failed to generate presigned URL: {e}")
        # Fallback to direct URL (only works for public buckets)
        return f"https://{MINIO_ENDPOINT}/{bucket}/{filename}"

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

=======
>>>>>>> 9355eb9c748ecb9a1101bd074f4c2566dd5191a0
def main():
    """Main function to process images from Redis queue"""
    logger.info("Starting AI service")
    
    try:
        # Initialize Redis
        r = initialize_redis()
        
        # Subscribe to the frames channel
        pubsub = r.pubsub()
        pubsub.subscribe(REDIS_CHANNEL_INPUT)
        logger.info(f"Subscribed to {REDIS_CHANNEL_INPUT} channel")
        
        while True:
            try:
                message = pubsub.get_message()
                if message and message['type'] == 'message':
                    data = message['data'].decode('utf-8')
                    try:
                        frame_info = eval(data)  # Parse the message data
                        
                        # Extract frame information
                        bucket = frame_info.get('bucket', MINIO_BUCKET)
                        filename = frame_info.get('filename')
                        
                        if not filename:
                            logger.error("No filename in message")
                            continue
                            
                        logger.info(f"Processing frame: {filename} from bucket: {bucket}")
                        
                        # Get image data from MinIO
                        image_data = minio_client.get_object(bucket, filename).read()
                        
                        # Process image
                        start_time = time.time()
                        processed_image, results, people_data = process_image(image_data, model)
                        processing_time = time.time() - start_time
                        
                        # Upload processed image
                        processed_filename = f"processed_{filename}"
                        original_url = get_minio_url(bucket, filename)
                        processed_url = get_minio_url(MINIO_BUCKET_PROCESSED, processed_filename)
                        minio_client.put_object(
                            MINIO_BUCKET_PROCESSED,
                            processed_filename,
                            processed_image,
                            processed_image.getbuffer().nbytes,
                            content_type='image/png'
                        )
                        logger.info(f"Uploaded processed image to {MINIO_BUCKET_PROCESSED}: {processed_filename}")
                        
                        # Format and publish results
                        result_data = format_result_data(
                            filename, bucket, processed_filename, MINIO_BUCKET_PROCESSED,
                            original_url, processed_url, processing_time, people_data
                        )
                        publish_result(r, REDIS_CHANNEL_OUTPUT, result_data)
                        
                    except Exception as e:
                        logger.error(f"Error processing image: {e}", exc_info=True)
                        # Publish error
                        error_data = format_error_data(
                            filename if 'filename' in locals() else None, 
                            e
                        )
                        publish_result(r, REDIS_CHANNEL_OUTPUT, error_data)
                
                time.sleep(0.1)  # Prevent CPU spinning
                
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                time.sleep(1)  # Wait before retrying
                
    except Exception as e:
        logger.error(f"Redis connection error: {e}", exc_info=True)
        raise

def test_process_images():
    """Test function to process all images in frames bucket"""
    logger.info("Starting test: Processing all images in frames bucket")
    
    try:
        # Initialize Redis
        r = initialize_redis()
        
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
                
                # Upload processed image
                processed_filename = f"test_processed_{filename}"
                original_url = get_minio_url(MINIO_BUCKET, filename)
                processed_url = get_minio_url(MINIO_BUCKET_PROCESSED_TEST, processed_filename)
                minio_client.put_object(
                    MINIO_BUCKET_PROCESSED_TEST,
                    processed_filename,
                    processed_image,
                    processed_image.getbuffer().nbytes,
                    content_type='image/png'
                )
                
                logger.info(f"Original image: {original_url}")
                logger.info(f"Processed image: {processed_url}")
<<<<<<< HEAD
                
                
                # Publish results
                result_data = {
                    'original_filename': filename,
                    'original_bucket': MINIO_BUCKET,
                    'processed_filename': processed_filename,
                    'processed_bucket': MINIO_BUCKET_PROCESSED_TEST,
                    'status': 'success',
                    'processing_time': processing_time,
                    'detections': {
                        'total_persons': len(people_data),
                        'people': people_data
                    }
                }
                
                r.publish('ai_results', str(result_data))
=======
                
                # Format and publish results
                result_data = format_result_data(
                    filename, MINIO_BUCKET, processed_filename, MINIO_BUCKET_PROCESSED_TEST,
                    original_url, processed_url, processing_time, people_data
                )
                publish_result(r, REDIS_CHANNEL_OUTPUT, result_data)
>>>>>>> 9355eb9c748ecb9a1101bd074f4c2566dd5191a0
                logger.info(f"Published results for {filename}")
                
                # Add delay between images
                time.sleep(2)
                
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
                publish_result(r, REDIS_CHANNEL_OUTPUT, error_data)
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

