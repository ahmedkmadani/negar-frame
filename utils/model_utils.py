import os
import logging
from ultralytics import YOLO
from .config import MODEL_CONFIG

logger = logging.getLogger(__name__)

AVAILABLE_MODELS = {
    # YOLOv8 Pose Models (Fast & Accurate)
    "yolov8n-pose": "hub:ultralytics/yolov8n-pose",  # Smallest & fastest
    "yolov8s-pose": "hub:ultralytics/yolov8s-pose",  # Small
    "yolov8m-pose": "hub:ultralytics/yolov8m-pose",  # Medium
    "yolov8l-pose": "hub:ultralytics/yolov8l-pose",  # Large
    "yolov8x-pose": "hub:ultralytics/yolov8x-pose",  # Extra Large, most accurate
    
    # YOLOv11 Pose Models - now available locally
    "yolov11n-pose": "hub:ultralytics/yolo11n.pt",  # Use the model downloaded in Dockerfile
    "yolov11s-pose": "hub:ultralytics/yolo11s.pt",  # Will need to add this to Dockerfile if used

    
    # YOLOv7 Pose Models (Good balance of speed/accuracy)
    "yolov7-pose": "hub:WongKinYiu/yolov7-pose",        # Base model
    "yolov7-w6-pose": "hub:WongKinYiu/yolov7-w6-pose",  # Wider version, more accurate
    
    # DWPose Models (State-of-the-art accuracy)
    "dw-pose": "hub:IDEA-Research/DWPose",              # Whole body pose estimation
    "dw-pose-mmpose": "hub:IDEA-Research/DWPose-mmpose", # Enhanced version
    
    # MMPose Models (High accuracy, research-focused)
    "mmpose-hrnet": "hub:openmmlab/hrnet",          # High-resolution network
    "mmpose-vitpose": "hub:openmmlab/vitpose",      # Vision Transformer based
    "mmpose-rtmpose": "hub:openmmlab/rtmpose",      # Real-time pose estimation
    
    # RTMPose Models (Optimized for real-time)
    "rtmpose-s": "hub:RTMPose/rtmpose-s",  # Small, fast
    "rtmpose-m": "hub:RTMPose/rtmpose-m",  # Medium
    "rtmpose-l": "hub:RTMPose/rtmpose-l",  # Large
    
    # AlphaPose Models (Popular in research)
    "alphapose": "hub:MVIG-SJTU/AlphaPose",
    
    # Specialized Models
    "mediapipe-pose": "hub:mediapipe/pose",          # Google's MediaPipe
    "openpose": "hub:CMU-Perceptual-Computing-Lab/openpose",  # Classic OpenPose
    
    # Multi-task Models (Pose + Other tasks)
    "yolo-nas-pose": "hub:damo-vilab/YOLO-NAS-pose",  # Neural Architecture Search based
    "vitpose-b": "hub:ViTPose/vitpose-b",            # ViT-based pose estimation
    "vitpose-l": "hub:ViTPose/vitpose-l",            # Larger ViT model
    
    # Real-world Optimized Models
    "efficient-pose": "hub:NVIDIA/efficient-pose",     # Efficiency-focused
    "lightweight-pose": "hub:Microsoft/lightweight-pose",  # Resource-friendly
}

def initialize_model(model_path=None, device=None):
    """Initialize the model from predefined models or direct HuggingFace path"""
    try:
        # Use provided parameters or defaults from config
        model_path = model_path or MODEL_CONFIG["model_name"]
        device = device or MODEL_CONFIG["device"]
        
        
        # If it's a predefined model, get its path
        if model_path in AVAILABLE_MODELS:
            model_path = AVAILABLE_MODELS[model_path]
        # If it's a direct HuggingFace path (contains '/'), add hub: prefix
        elif '/' in model_path:
            model_path = f"hub:{model_path}"
        
        logger.info(f"Loading model from: {model_path}")
        model = YOLO(model_path).to(device)
        
        model.conf = MODEL_CONFIG["confidence_threshold"]
        model.imgsz = 640
        
        logger.info(f"Model loaded successfully")
        return model
    except Exception as e:
        logger.error(f"Error loading model: {e}", exc_info=True)
        raise

def list_available_models():
    """List all predefined models with their categories"""
    categories = {}
    for model_name in AVAILABLE_MODELS:
        category = model_name.split('-')[0].upper()
        if category not in categories:
            categories[category] = []
        categories[category].append(model_name)
    return categories

def add_model(name, path):
    """Add a new model to the available models"""
    if not path.startswith('hub:'):
        path = f"hub:{path}"
    AVAILABLE_MODELS[name] = path
    logger.info(f"Added new model: {name} -> {path}") 