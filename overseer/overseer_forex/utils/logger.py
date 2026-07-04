"""
Logging utility for OVERSEER
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
import os


def setup_logger(name: str = "overseer") -> logging.Logger:
    """Setup rotating file logger with console output."""
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, os.getenv('LOG_LEVEL', 'INFO')))
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console.setFormatter(console_format)
    logger.addHandler(console)
    
    # File handler with rotation
    log_dir = Path(os.getenv('LOG_PATH', './logs')).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    file_handler = RotatingFileHandler(
        os.getenv('LOG_PATH', './logs/overseer.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    return logger
