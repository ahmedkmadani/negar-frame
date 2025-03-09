import os
import logging
from ultralytics import YOLO
from .config import MODEL_CONFIG

logger = logging.getLogger(__name__)

def initialize_model(model_path=None, device=None):
    """Initialize the YOLO model"""
    try:
        # Use provided parameters or defaults from config
        model_path = model_path or MODEL_CONFIG["path"]
        device = device or MODEL_CONFIG["device"]
        
        logger.info(f"Loading YOLO model from {model_path} on {device}")
        model = YOLO(model_path).to(device)
        logger.info("YOLO model loaded successfully")
        return model
    except Exception as e:
        logger.error(f"Error loading YOLO model: {e}", exc_info=True)
        raise 