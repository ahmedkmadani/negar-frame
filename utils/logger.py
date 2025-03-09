import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logger(name: str, log_file: str = None, level=logging.INFO) -> logging.Logger:
    """
    Setup logger with both file and console handlers
    
    Args:
        name (str): Logger name (usually __name__ from the calling module)
        log_file (str): Path to log file (optional)
        level: Logging level (default: INFO)
    
    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)

    return logger

# Create default logger instance with configurable name
def get_logger(service_name: str) -> logging.Logger:
    """
    Get a configured logger instance for a specific service
    
    Args:
        service_name (str): Name of the service to create logger for
    
    Returns:
        logging.Logger: Configured logger instance
    """
    return setup_logger(name=service_name)
