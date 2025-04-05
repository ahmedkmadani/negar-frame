import logging
import cv2
import numpy as np
from PIL import Image, ImageDraw
import io

logger = logging.getLogger(__name__)

def process_image(image_data, model):
    """
    Process an image with the YOLO model to detect people and their keypoints.
    Uses multi-attempt detection with different preprocessing and confidence levels
    when initial detection fails.
    
    Args:
        image_data: Binary image data
        model: YOLO model instance
        
    Returns:
        tuple: (processed_image, results, people_data)
    """
    logger.info("\n" + "="*50)
    logger.info(f"Processing image")
    logger.info("="*50 + "\n")
            
    # Decode image
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.COLOR_BGR2RGB)
    
    # Get original image dimensions
    original_height, original_width = img.shape[:2]
    
    image_size = (original_height, original_width)
    logger.info(f"Processing image with original dimensions: {original_width}x{original_height}")
    
    # Multi-attempt detection with progressively more aggressive settings
    logger.info("Attempt 1: Using original image with standard settings...")
    # First try with standard settings
    results = model(img, imgsz=image_size, conf=0.4, iou=0.5, verbose=False)
    
    # If no detections or very few, try with enhanced image and lower confidence
    # if len(results) == 0 or not hasattr(results[0], 'boxes') or len(results[0].boxes) == 0:
    #     logger.info("No detections in attempt 1, trying attempt 2 with enhanced image...")
        
    #     # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to enhance image
    #     lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    #     l, a, b = cv2.split(lab)
    #     clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    #     cl = clahe.apply(l)
    #     enhanced_lab = cv2.merge((cl, a, b))
    #     img_enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
        
    #     # Try with enhanced image, higher resolution, and lower confidence
    #     results = model(img_enhanced, imgsz=1280, conf=0.05, iou=0.4, verbose=False)
        
    #     # If still no detections, try with original image and even lower confidence
    #     if len(results) == 0 or not hasattr(results[0], 'boxes') or len(results[0].boxes) == 0:
    #         logger.info("No detections in attempt 2, trying attempt 3 with contrast enhancement...")
            
    #         # Apply contrast enhancement
    #         alpha = 1.5  # Contrast control (1.0 means no change)
    #         beta = 15    # Brightness control (0 means no change)
    #         img_contrast = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
            
    #         results = model(img_contrast, imgsz=1920, conf=0.03, iou=0.3, verbose=False)
            
    #         # If still no detections, try final attempt with extremely low confidence
    #         if len(results) == 0 or not hasattr(results[0], 'boxes') or len(results[0].boxes) == 0:
    #             logger.info("No detections in attempt 3, trying final attempt with extremely low confidence...")
    #             results = model(img, imgsz=1920, conf=0.01, iou=0.2, verbose=False)
    
    # Log detection results
    detected_persons = False
    if len(results) > 0 and hasattr(results[0], 'boxes') and len(results[0].boxes) > 0:
        logger.info(f"Successfully detected {len(results[0].boxes)} objects")
        detected_persons = True
    else:
        logger.info("No people detected after all attempts")
            
    # Convert to PIL image for drawing
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
            
    # Initialize people_data list to store all detected persons
    people_data = []
    
    # Define colors for different joint groups
    color_map = {
        "head": (255, 0, 0),       # Red for head
        "upper_body": (0, 255, 0), # Green for upper body
        "lower_body": (0, 0, 255)  # Blue for lower body
    }
    
    # Only process detections if we have valid results
    persons = []
    if detected_persons:
        # Filter persons with confidence > model.conf
        persons = [(i, box) for i, box in enumerate(results[0].boxes.data) 
                    if int(box[5]) == 0 and box[4] > model.conf]
        
        logger.info(f"Found {len(persons)} person(s) with confidence > {model.conf}\n")
        
        # If no persons were found after filtering, update detected_persons flag
        if len(persons) == 0:
            detected_persons = False
            logger.info("No people detected with sufficient confidence")
        
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
                    "head": ["nose", "left_eye", "right_eye", "left_ear", "right_ear"],
                    "upper_body": ["left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"],
                    "lower_body": ["left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"]
                }
                
                keypoint_names = [
                    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
                    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                    "left_wrist", "right_wrist", "left_hip", "right_hip",
                    "left_knee", "right_knee", "left_ankle", "right_ankle"
                ]
                
                # Log and draw keypoints with different colors based on body part
                for group_name, joints in joint_groups.items():
                    color = color_map[group_name]
                    
                    # Initialize group data
                    group_data = {}
                    
                    for joint_name in joints:
                        joint_idx = keypoint_names.index(joint_name)
                        
                        # Get keypoint coordinates and confidence
                        x, y, joint_conf = keypoints[joint_idx]
                        
                        # Only process if joint is detected with sufficient confidence
                        if joint_conf > 0.5:
                            logger.info(f"  {joint_name}: ({x:.1f}, {y:.1f}) conf: {joint_conf:.2f}")
                            
                            # Draw circle for the joint
                            draw.ellipse([x-5, y-5, x+5, y+5], fill=color)
                            
                            # Add text label
                            draw.text((x+7, y-7), joint_name.replace('_', ' '), fill=color)
                            
                            # Store joint data
                            group_data[joint_name] = {
                                "x": float(x),
                                "y": float(y),
                                "confidence": float(joint_conf)
                            }
                    
                    # Add group data to person data if any joints were detected
                    if group_data:
                        if len(people_data) <= person_idx:
                            people_data.append({})
                        people_data[person_idx][group_name] = group_data
                
                # Draw skeleton lines to connect joints
                skeleton_connections = [
                    # Head
                    ("nose", "left_eye"), ("nose", "right_eye"),
                    ("left_eye", "left_ear"), ("right_eye", "right_ear"),
                    # Upper body
                    ("left_shoulder", "right_shoulder"), 
                    ("left_shoulder", "left_elbow"), ("right_shoulder", "right_elbow"),
                    ("left_elbow", "left_wrist"), ("right_elbow", "right_wrist"),
                    # Torso
                    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
                    # Lower body
                    ("left_hip", "right_hip"),
                    ("left_hip", "left_knee"), ("right_hip", "right_knee"),
                    ("left_knee", "left_ankle"), ("right_knee", "right_ankle")
                ]
                
                for start_joint, end_joint in skeleton_connections:
                    start_idx = keypoint_names.index(start_joint)
                    end_idx = keypoint_names.index(end_joint)
                    
                    start_x, start_y, start_conf = keypoints[start_idx]
                    end_x, end_y, end_conf = keypoints[end_idx]
                    
                    # Only draw if both joints are detected with sufficient confidence
                    if start_conf > 0.5 and end_conf > 0.5:
                        # Determine line color based on the body part
                        if start_joint in joint_groups["head"] and end_joint in joint_groups["head"]:
                            line_color = color_map["head"]
                        elif start_joint in joint_groups["upper_body"] and end_joint in joint_groups["upper_body"]:
                            line_color = color_map["upper_body"]
                        elif start_joint in joint_groups["lower_body"] and end_joint in joint_groups["lower_body"]:
                            line_color = color_map["lower_body"]
                        else:
                            # For connections between different body parts (e.g., shoulder to hip)
                            line_color = (255, 255, 0)  # Yellow
                        
                        draw.line([start_x, start_y, end_x, end_y], fill=line_color, width=2)
                
                # Add person metadata
                if len(people_data) <= person_idx:
                    people_data.append({})
                
                people_data[person_idx]["bounding_box"] = {
                    "x1": float(x1),
                    "y1": float(y1),
                    "x2": float(x2),
                    "y2": float(y2)
                }
                people_data[person_idx]["confidence"] = float(conf)
    
    # Only add legend if people were detected
    if detected_persons and len(persons) > 0:
        # Add a legend
        legend_x = 20
        legend_y = 20
        legend_spacing = 25
        
        # Semi-transparent background for legend
        draw.rectangle(
            [legend_x - 10, legend_y - 10, legend_x + 150, legend_y + (len(color_map) * legend_spacing) + 10],
            fill=(255, 255, 255, 180)
        )
        
        # Add legend title
        draw.text((legend_x, legend_y), "Joint Groups:", fill=(0, 0, 0))
        legend_y += 25
        
        # Add color codes
        for i, (group, color) in enumerate(color_map.items()):
            y_pos = legend_y + (i * legend_spacing)
            
            # Draw color box
            draw.rectangle(
                [legend_x + 10, y_pos, legend_x + 20, y_pos + 10], 
                fill=color, 
                outline=(0, 0, 0)
            )
            
            # Draw label
            draw.text(
                (legend_x + 30, y_pos - 2), 
                group.replace("_", " ").title(), 
                fill=(0, 0, 0)
            )
    else:
        # Add a message when no people are detected
        message = "No people detected"
        # Calculate text position to center it in the image
        text_width = len(message) * 10  # Approximate width of text
        text_x = (original_width - text_width) // 2
        text_y = original_height // 2
        
        # Add semi-transparent background for text
        text_padding = 10
        draw.rectangle(
            [text_x - text_padding, text_y - text_padding, 
             text_x + text_width + text_padding, text_y + 20 + text_padding],
            fill=(255, 255, 255, 180)
        )
        
        # Draw the message
        draw.text((text_x, text_y), message, fill=(255, 0, 0))
    
    # Save the processed image to a byte array
    img_byte_arr = io.BytesIO()
    img_pil.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    # Return both the processed image and the results
    return img_byte_arr, results, people_data 