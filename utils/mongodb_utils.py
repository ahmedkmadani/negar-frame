import os
from pymongo import MongoClient
import logging
from .config import MONGO_CONFIG

logger = logging.getLogger(__name__)

MONGO_HEATMAP_HISTORY_COLLECTION = MONGO_CONFIG["collections"]["heatmap_history"]
MONGO_HEATMAP_COLLECTION = MONGO_CONFIG["collections"]["heatmap"]

MONGO_DB = MONGO_CONFIG["db"]
MONGO_USERNAME = MONGO_CONFIG["username"]
MONGO_PASSWORD = MONGO_CONFIG["password"]
MONGO_HOST = MONGO_CONFIG["host"]
MONGO_PORT = MONGO_CONFIG["port"]



MONGO_URI = f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}?authSource=admin"


logger.info(f"Connecting to MongoDB at {MONGO_URI}")
try:
    mongo_client = MongoClient(MONGO_URI)
    # Test the connection
    mongo_client.admin.command('ping')
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"Error connecting to MongoDB: {str(e)}")
    logger.error("Please verify your MongoDB credentials and connection details")
    raise


