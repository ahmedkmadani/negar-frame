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
                
                # Format and publish results
                result_data = format_result_data(
                    filename, MINIO_BUCKET, processed_filename, MINIO_BUCKET_PROCESSED_TEST,
                    original_url, processed_url, processing_time, people_data
                )
                publish_result(r, REDIS_CHANNEL_OUTPUT, result_data)
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

