import logging
import cv2
import numpy as np
from PIL import Image, ImageDraw
import io

logger = logging.getLogger(__name__)

def process_image(image_data, model):
    """
    Process an image with the YOLO model to detect people and their keypoints.
    
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
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
    # Run detection
    results = model(img)
            
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
    
    # Save the processed image to a byte array
    img_byte_arr = io.BytesIO()
    img_pil.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    # Return both the processed image and the results
    return img_byte_arr, results, people_data 